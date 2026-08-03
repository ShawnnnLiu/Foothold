"""The petition-writer node (docs/implementation-plans/llm-nodes/01-petition-writer.md).

The vocabulary gate, second half: the findings bundle handed to the prompt IS
the object the citation validator checks the drafted letter against. Both
vocabularies are computed from the bundle and nothing else, so a letter can
only cite what a selected finding already carries.

`write_petition` never raises. A `GenerationError` with `repair_limit_exceeded`
takes the deterministic template-letter fallback (a success with a recorded
reason the LLM draft was discarded); every other `GenerationError` becomes a
typed `failed` petition.
"""

import json
import re
from collections.abc import Iterator, Sequence
from typing import Any

from starmap.common.clock import Clock
from starmap.contracts.evaluation import Evaluation
from starmap.contracts.petition import CitedCourse, Petition, PetitionDraft
from starmap.contracts.reason_codes import LlmReasonCode, TriageBucket
from starmap.llm.engine import AdapterConfig, GenerationEngine
from starmap.llm.errors import GenerationError
from starmap.llm.transport_anthropic import (
    SONNET_5_INPUT_PRICE_PER_MTOK,
    SONNET_5_OUTPUT_PRICE_PER_MTOK,
)

# Locked in docs/implementation-plans/llm-nodes/00-overview.md decision 2: a
# letter is capped at 8000 characters (roughly 2000 tokens) plus JSON envelope,
# so 3000 output tokens is pure headroom with thinking pinned off.
PETITION_WRITER_CONFIG = AdapterConfig(
    model_name="claude-sonnet-5",
    prompt_version="petition-writer-v1",
    max_tokens=3000,
    input_price_per_mtok=SONNET_5_INPUT_PRICE_PER_MTOK,
    output_price_per_mtok=SONNET_5_OUTPUT_PRICE_PER_MTOK,
)

SELECTABLE_BUCKETS = frozenset({TriageBucket.AT_RISK, TriageBucket.NO_ARTICULATION})

# petition-writer-v1 (2026-08-03): initial version. The source is wrapped for
# line length only; the rendered bytes are pinned in tests/test_prompt_pins.py.
PETITION_WRITER_SYSTEM = (
    "You draft petition letters for California community college transfer students.\n"
    "A deterministic evaluator has already compared the student's courses against the "
    "official ASSIST articulation agreement; you receive its findings object.\n"
    "Write a formal, respectful letter to the receiving university's transfer credit "
    "office asking for review of the at-risk and unarticulated credits.\n"
    "\n"
    "Hard rules:\n"
    "- Ground every claim in the findings object. It is the only source of truth.\n"
    "- Cite only course codes, agreement keys, and year labels that appear in the "
    "findings object. Never invent a course, policy, department, person, date, or deadline.\n"
    "- For each finding that carries a citation, mention its agreement key and year "
    "label once.\n"
    "- Request review; never state or imply a guaranteed outcome.\n"
    "- The only placeholder allowed is [Your name] on the signature line.\n"
    "- Do not write uppercase abbreviations followed by numbers (unit totals, GPA "
    "figures, form numbers) unless they are course codes from the findings object.\n"
    "- Plain text only: no markdown, no headings, no bullet characters.\n"
    '- Structure: the greeting "Dear Transfer Credit Evaluator,", one opening paragraph '
    "naming the sending institution, receiving institution, and intended major, one "
    "paragraph per finding in the given order, one closing paragraph, then "
    '"Sincerely," and "[Your name]".\n'
    "\n"
    'Return a JSON object with exactly one key, "letter_text", holding the complete letter.'
)

USER_PROMPT_HEADER = (
    "Draft the petition letter for the findings below.\n"
    "\n"
    "FINDINGS OBJECT (canonical JSON, the only ground truth you may cite):\n"
)

# Scan patterns over LETTER text, deliberately looser than the validating
# `contracts/codes.COURSE_CODE_RE` and `contracts/agreement.ASSIST_KEY_PATTERN`:
# they must CATCH anything code-shaped or key-shaped the model wrote, then
# membership in the bundle-derived vocabulary decides legitimacy. The recorded
# trade-off: benign uppercase-plus-number tokens (a "GPA 3.8") are flagged and
# cost one repair round; the alternative is an invented citation surviving into
# a letter a student mails.
CODE_SCAN_RE = re.compile(
    r"(?<![A-Z0-9])"
    r"[A-Z][A-Z0-9&/.\-]{1,9}(?: [A-Z&][A-Z0-9&/.\-]{0,9}){0,2}"
    r" -?[A-Z]{0,3}[0-9]{1,4}(?:\.[0-9]{1,2})?(?:[A-Z+\-][A-Z0-9+\-]{0,3})?(?: [A-Z]{1,2})?"
    r"(?![A-Z0-9])"
)
KEY_SCAN_RE = re.compile(r"[0-9]{1,4}/[0-9]{1,4}/to/[0-9]{1,4}/(?:Major|Department)/[^\s,.;:)]+")


def build_findings_bundle(
    evaluation: Evaluation,
    finding_positions: Sequence[int],
    *,
    sending_name: str,
    receiving_name: str,
    major_label: str,
) -> dict[str, Any]:
    """The prompt-bound findings object: SELECTED findings only, ascending.

    Preconditions are asserts, not validation: N3's route 422s bad positions
    before a job is scheduled, so a violation here is a programming error.
    """
    findings: list[dict[str, Any]] = []
    for position in sorted(finding_positions):
        assert 0 <= position < len(evaluation.findings), (
            f"finding position {position} is out of range for {len(evaluation.findings)} findings"
        )
        finding = evaluation.findings[position]
        assert finding.bucket in SELECTABLE_BUCKETS, (
            f"finding {position} has bucket {finding.bucket.value!r}, which is not petitionable"
        )
        citation = None
        if finding.citation is not None:
            citation = {
                "assist_key": finding.citation.assist_key,
                "position": finding.citation.position,
                "year_label": finding.citation.year_label,
            }
        findings.append(
            {
                "position": position,
                "code": finding.code.value,
                "bucket": finding.bucket.value,
                "student_course_codes": list(finding.student_course_codes),
                "receiving_course_code": finding.receiving_course_code,
                "receiving_course_title": finding.receiving_course_title,
                "units": finding.units,
                "citation": citation,
                "advisements": list(finding.advisements),
                "detail": finding.detail,
            }
        )
    return {
        "sending_institution": sending_name,
        "receiving_institution": receiving_name,
        "major": major_label,
        "year_label": evaluation.year_label,
        "findings": findings,
    }


def build_user_prompt(bundle: dict[str, Any]) -> str:
    """Canonical serialization (00-overview.md decision 9) keeps the bytes stable."""
    return USER_PROMPT_HEADER + json.dumps(bundle, sort_keys=True, indent=2)


def _collapse_code(token: str) -> str:
    """`normalize_course_code`-style collapsing without its validation."""
    return " ".join(token.upper().split())


def _prose_fields(finding: dict[str, Any]) -> Iterator[str]:
    if finding["receiving_course_title"] is not None:
        yield finding["receiving_course_title"]
    if finding["detail"] is not None:
        yield finding["detail"]
    yield from finding["advisements"]


def allowed_course_codes(bundle: dict[str, Any]) -> frozenset[str]:
    """Every course code a selected finding carries, prose fields included.

    The prose fields are scanned because the evaluator's deterministic text may
    itself name agreement courses (a `partial_series` detail names the missing
    series member), and anything inside the findings object is legitimately
    citeable.
    """
    allowed: set[str] = set()
    for finding in bundle["findings"]:
        allowed.update(finding["student_course_codes"])
        if finding["receiving_course_code"] is not None:
            allowed.add(finding["receiving_course_code"])
        for text in _prose_fields(finding):
            for match in CODE_SCAN_RE.finditer(text):
                allowed.add(_collapse_code(match.group(0)))
    return frozenset(allowed)


def allowed_agreement_keys(bundle: dict[str, Any]) -> frozenset[str]:
    """Every agreement key a selected finding carries.

    Prose fields are scanned for the same reason as in `allowed_course_codes`:
    a `double_count_risk` detail names the sibling agreement key it also
    applied at, and the template letter echoes that detail verbatim, so a
    key inside the findings object must be citeable or the deterministic
    fallback would fail its own validator.
    """
    allowed: set[str] = set()
    for finding in bundle["findings"]:
        if finding["citation"] is not None:
            allowed.add(finding["citation"]["assist_key"])
        for text in _prose_fields(finding):
            allowed.update(match.group(0) for match in KEY_SCAN_RE.finditer(text))
    return frozenset(allowed)


def _code_appears(code: str, letter_text: str) -> bool:
    pattern = r"(?<![A-Z0-9])" + re.escape(code) + r"(?![A-Z0-9])"
    return re.search(pattern, letter_text) is not None


def validate_citations(letter_text: str, bundle: dict[str, Any]) -> None:
    """Raise one `ValueError` listing EVERY violation, so the repair re-prompt
    quotes the full set. Never raises `GenerationError`."""
    codes = allowed_course_codes(bundle)
    keys = allowed_agreement_keys(bundle)
    violations: list[str] = []
    for match in CODE_SCAN_RE.finditer(letter_text):
        if _collapse_code(match.group(0)) not in codes:
            violations.append(
                f"course code {match.group(0)!r} does not appear in the findings object"
            )
    for match in KEY_SCAN_RE.finditer(letter_text):
        if match.group(0) not in keys:
            violations.append(
                f"agreement key {match.group(0)!r} does not appear in the findings object"
            )
    for finding in bundle["findings"]:
        candidates = list(finding["student_course_codes"])
        if finding["receiving_course_code"] is not None:
            candidates.append(finding["receiving_course_code"])
        if candidates and not any(_code_appears(code, letter_text) for code in candidates):
            violations.append(
                f"selected finding at position {finding['position']} is unaddressed; "
                f"the letter must mention one of: {', '.join(candidates)}"
            )
    if violations:
        raise ValueError("; ".join(violations))


def compute_cited(letter_text: str, bundle: dict[str, Any]) -> list[CitedCourse]:
    """Deterministic citation index, in (ascending position, stored code order).

    No deduplication across findings: a course serving two selected findings
    yields two entries, and this order is the locked tie-break the UI consumes.
    """
    cited: list[CitedCourse] = []
    for finding in bundle["findings"]:
        for code in finding["student_course_codes"]:
            if _code_appears(code, letter_text):
                cited.append(CitedCourse(course_code=code, finding_position=finding["position"]))
    return cited


def _format_codes(codes: Sequence[str]) -> str:
    if len(codes) <= 1:
        return "".join(codes)
    return ", ".join(codes[:-1]) + " and " + codes[-1]


def _finding_paragraph(finding: dict[str, Any]) -> str:
    codes = _format_codes(finding["student_course_codes"])
    if finding["code"] == "no_articulation":
        return (
            f"The agreement lists no articulation for {codes}. I respectfully request an "
            f"individual review of this coursework for transfer credit, and I can provide "
            f"the official course outline of record on request."
        )
    if finding["code"] == "unresolved":
        subject = codes if finding["student_course_codes"] else "my records"
        return (
            f"My records also include coursework ({subject}) that could not be matched "
            f"against the college's current course list. I can provide documentation to "
            f"resolve it."
        )
    citation = finding["citation"]
    assert citation is not None, f"at-risk finding {finding['position']} carries no citation"
    target = (
        finding["receiving_course_code"]
        or finding["receiving_course_title"]
        or "the articulated requirement"
    )
    detail_clause = (
        f"; the evaluation noted: {finding['detail']}" if finding["detail"] is not None else ""
    )
    return (
        f"I ask that {codes} be reviewed toward {target}{detail_clause} "
        f"(agreement {citation['assist_key']}, {citation['year_label']})."
    )


def render_template_letter(bundle: dict[str, Any]) -> str:
    """The deterministic fallback letter; pure, findings in ascending position order."""
    paragraphs = [
        "Dear Transfer Credit Evaluator,",
        (
            f"I am writing to request a review of several courses I completed at "
            f"{bundle['sending_institution']}, as part of my application to the "
            f"{bundle['major']} program at {bundle['receiving_institution']}. The "
            f"{bundle['year_label']} ASSIST articulation agreement for this pair supports "
            f"the requests below."
        ),
    ]
    paragraphs.extend(_finding_paragraph(finding) for finding in bundle["findings"])
    paragraphs.append("Thank you for your time and consideration.")
    paragraphs.append("Sincerely,\n[Your name]")
    return "\n\n".join(paragraphs)


def write_petition(
    *,
    petition_id: str,
    evaluation: Evaluation,
    finding_positions: Sequence[int],
    sending_name: str,
    receiving_name: str,
    major_label: str,
    engine: GenerationEngine[PetitionDraft],
    clock: Clock,
) -> Petition:
    """Run the node and return a typed `Petition`; never raises."""
    bundle = build_findings_bundle(
        evaluation,
        finding_positions,
        sending_name=sending_name,
        receiving_name=receiving_name,
        major_label=major_label,
    )
    user_prompt = build_user_prompt(bundle)
    try:
        draft = engine.generate(
            run_id=petition_id,
            system=PETITION_WRITER_SYSTEM,
            user_prompt=user_prompt,
            post_validate=lambda d: validate_citations(d.letter_text, bundle),
        )
    except GenerationError as error:
        if error.llm_reason_code is LlmReasonCode.REPAIR_LIMIT_EXCEEDED:
            letter_text = render_template_letter(bundle)
            return Petition(
                petition_id=petition_id,
                evaluation_id=evaluation.evaluation_id,
                finding_positions=list(finding_positions),
                status="succeeded",
                reason_code=error.llm_reason_code,
                fallback=True,
                letter_text=letter_text,
                cited=compute_cited(letter_text, bundle),
                created_at=clock.now(),
            )
        return Petition(
            petition_id=petition_id,
            evaluation_id=evaluation.evaluation_id,
            finding_positions=list(finding_positions),
            status="failed",
            reason_code=error.llm_reason_code,
            fallback=False,
            letter_text=None,
            cited=[],
            created_at=clock.now(),
        )
    return Petition(
        petition_id=petition_id,
        evaluation_id=evaluation.evaluation_id,
        finding_positions=list(finding_positions),
        status="succeeded",
        reason_code=None,
        fallback=False,
        letter_text=draft.letter_text,
        cited=compute_cited(draft.letter_text, bundle),
        created_at=clock.now(),
    )
