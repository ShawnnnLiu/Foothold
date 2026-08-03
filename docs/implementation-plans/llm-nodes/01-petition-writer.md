# Increment N1: Petition Writer Node

Goal: the petition contract stack and `llm/petition_writer.py`, the node that turns a stored evaluation's selected findings into a grounded draft letter, with the citation validator and the deterministic template fallback.
No HTTP surface in this increment; N3 exposes it.
Binding references: `docs/FOOTHOLD_PATHFINDERS_PLAN.md:155-162`, the vocabulary-gate axiom (`CLAUDE.md`: the findings object given to the petition prompt IS the set the citation validator checks the letter against), TR 4.1/4.2/4.6, and the wire shapes in `docs/implementation-plans/frontend/05-petition-parse-ui.md`.

Contract-discipline order (`CLAUDE.md`, "Schema And Contract Rules"): spec doc first, then the contract module, fixtures, regenerated JSON schemas, node code, tests.

## Files

| Path | Content |
| --- | --- |
| `docs/specs/petition.schema.md` | New spec, content locked below. |
| `backend/src/starmap/contracts/petition.py` | `PetitionDraft`, `CitedCourse`, `Petition`. |
| `backend/src/starmap/llm/petition_writer.py` | Config, prompts, bundle builder, citation validator, template letter, `write_petition`. |
| `backend/tests/contracts/test_petition.py` + `backend/tests/fixtures/{valid,invalid}/petition/` | Fixture harness rows, one named invalid fixture per constraint and validator. |
| `backend/tests/llm/test_petition_writer.py` | The FakeTransport suite and both prompt-pin layers. |
| `backend/schemas/petition.schema.json` | Generated; wire `Petition` (and `PetitionDraft`) into `backend/scripts/generate_schemas.py` the same way existing contracts are listed. |
| `backend/tests/test_prompt_pins.py` | Add the `PETITION_WRITER_SYSTEM` row to `SYSTEM_PROMPT_PINS`. |

## Contracts (`contracts/petition.py`)

All models use `contracts.base.FROZEN`; text hygiene is `contracts.base.reject_control_chars` (it already admits `\n`, `\r`, `\t`, which letters need).

### PetitionDraft (the LLM output contract)

| Field | Type | Constraints |
| --- | --- | --- |
| `letter_text` | str | min 200, max 8000 chars; `reject_control_chars`. |

One key on purpose: the letter is the whole proposal, and every other wire field is computed deterministically.
The 200-char floor rejects degenerate output cheaply at the schema gate, where it produces a repairable violation.

### CitedCourse

| Field | Type | Constraints |
| --- | --- | --- |
| `course_code` | `codes.CourseCode` | Normalized; these values come from `Finding.student_course_codes`, which are already normalized. |
| `finding_position` | int | `ge=0`. |

### Petition (the stored and polled artifact)

| Field | Type | Constraints |
| --- | --- | --- |
| `petition_id` | str | Pattern `^pet_[0-9a-f]{16}$`; minted via `IdGenerator.new_id("pet")`. |
| `evaluation_id` | str | Pattern `^eval_[0-9a-f]{16}$` (same pattern as `Evaluation.evaluation_id`). |
| `finding_positions` | list[int] | Min length 1; each `ge=0`; validator: strictly ascending (which enforces uniqueness). |
| `status` | `Literal["pending", "succeeded", "failed"]` | |
| `reason_code` | `LlmReasonCode \| None` | Default `None`. |
| `fallback` | bool | Default `False`. |
| `letter_text` | str \| None | Default `None`; when present, the `PetitionDraft` constraints (200..8000, hygiene). |
| `cited` | list[CitedCourse] | Default empty. |
| `created_at` | datetime | Timezone-aware (same validator pattern as `LlmCallLogRecord`). |

Validators, each with a named invalid fixture:

| Validator | Rule |
| --- | --- |
| positions ascending | `finding_positions` strictly ascending; the error quotes the list. |
| pending shape | `status == "pending"` requires `letter_text` null, `cited` empty, `fallback` false, `reason_code` null. |
| succeeded shape | `status == "succeeded"` requires `letter_text` non-null, and `reason_code` non-null IFF `fallback` is true (both directions). |
| failed shape | `status == "failed"` requires `letter_text` null, `cited` empty, `fallback` false, `reason_code` non-null. |
| cited positions selected | Every `cited[].finding_position` is a member of `finding_positions`. |
| created_at tz-aware | Naive datetimes rejected, quoting the ISO value. |

The `fallback` flag lives only on `succeeded` by construction: a fallback letter is a success with a recorded reason the LLM draft was discarded (doc 05).

### Spec fixtures (locked names)

Valid: `pending.json`, `succeeded.json`, `succeeded_fallback.json`, `failed.json`, `draft_minimal.json`.
Invalid: `bad_petition_id`, `bad_evaluation_id`, `empty_positions`, `negative_position`, `unsorted_positions`, `duplicate_positions`, `pending_with_letter`, `pending_with_reason_code`, `pending_with_fallback`, `succeeded_without_letter`, `succeeded_reason_without_fallback`, `succeeded_fallback_without_reason`, `failed_without_reason`, `failed_with_letter`, `cited_position_not_selected`, `cited_bad_course_code`, `letter_too_short`, `letter_too_long`, `letter_control_char`, `naive_created_at`, `draft_missing_letter`, `draft_extra_key`.
Each invalid fixture carries its `.expected.json` per the existing harness pattern in `backend/tests/fixtures/invalid/llm_call_log/`.

## The findings bundle (the vocabulary gate, second half)

`build_findings_bundle(evaluation, finding_positions, *, sending_name, receiving_name, major_label) -> dict`.

Selection precondition (assert, not validate: N3's route already 422s bad positions): every position indexes `evaluation.findings` and references a finding whose `bucket` is `TriageBucket.AT_RISK` or `TriageBucket.NO_ARTICULATION`.
The bundle contains ONLY the selected findings; nothing from an unselected finding may reach the prompt (pinned by a rot-guard test below).

Locked bundle shape (plain dict, serialized with the canonical rule from `00-overview.md` decision 9):

```json
{
  "sending_institution": "<sending_name>",
  "receiving_institution": "<receiving_name>",
  "major": "<major_label>",
  "year_label": "<evaluation.year_label>",
  "findings": [
    {
      "position": 3,
      "code": "<finding.code.value>",
      "bucket": "<finding.bucket.value>",
      "student_course_codes": ["..."],
      "receiving_course_code": "... or null",
      "receiving_course_title": "... or null",
      "units": 4.0,
      "citation": {"assist_key": "...", "position": 5, "year_label": "..."},
      "advisements": ["..."],
      "detail": "... or null"
    }
  ]
}
```

`findings` are ordered by ascending position.
Institution names and the major label are caller-supplied strings because `Evaluation` carries only ids and keys; N3's route resolves them from `ArticulationStore` before scheduling the job.

## Prompts

Both constants live in `llm/petition_writer.py` with a dated changelog comment (`# petition-writer-v1 (<commit date>): initial version.`).

`PETITION_WRITER_SYSTEM`, locked text:

```
You draft petition letters for California community college transfer students.
A deterministic evaluator has already compared the student's courses against the official ASSIST articulation agreement; you receive its findings object.
Write a formal, respectful letter to the receiving university's transfer credit office asking for review of the at-risk and unarticulated credits.

Hard rules:
- Ground every claim in the findings object. It is the only source of truth.
- Cite only course codes, agreement keys, and year labels that appear in the findings object. Never invent a course, policy, department, person, date, or deadline.
- For each finding that carries a citation, mention its agreement key and year label once.
- Request review; never state or imply a guaranteed outcome.
- The only placeholder allowed is [Your name] on the signature line.
- Do not write uppercase abbreviations followed by numbers (unit totals, GPA figures, form numbers) unless they are course codes from the findings object.
- Plain text only: no markdown, no headings, no bullet characters.
- Structure: the greeting "Dear Transfer Credit Evaluator,", one opening paragraph naming the sending institution, receiving institution, and intended major, one paragraph per finding in the given order, one closing paragraph, then "Sincerely," and "[Your name]".

Return a JSON object with exactly one key, "letter_text", holding the complete letter.
```

User prompt, built by `build_user_prompt(bundle)`, locked template:

```
Draft the petition letter for the findings below.

FINDINGS OBJECT (canonical JSON, the only ground truth you may cite):
<json.dumps(bundle, sort_keys=True, indent=2)>
```

The repair suffix is the engine's; this node never concatenates feedback into the user prompt.

## The citation validator (`validate_citations`)

`validate_citations(letter_text: str, bundle: dict) -> None`, raising a single `ValueError` that lists EVERY violation (TR 3.6: collect all violations into one error so the repair re-prompt quotes the full set), and never raising `GenerationError`.

Allowed vocabularies, computed from the bundle only:

1. Allowed course codes: the union over selected findings of `student_course_codes`, `receiving_course_code` (when present), and every course-code-shaped token found by `CODE_SCAN_RE` inside `receiving_course_title`, `detail`, and each `advisements` entry.
   The prose fields are included because the evaluator's deterministic text may itself name agreement courses (a `partial_series` detail names the missing series member), and anything inside the findings object is legitimately citeable.
2. Allowed agreement keys: the set of `citation.assist_key` values on selected findings.
3. Year labels never need allowing: the scan patterns below cannot match a bare `2025-2026`.

Locked scan patterns (module constants, with a comment tying them to `contracts/codes.py` and `contracts/agreement.ASSIST_KEY_PATTERN`):

```python
CODE_SCAN_RE = re.compile(
    r"(?<![A-Z0-9])"
    r"[A-Z][A-Z0-9&/.\-]{1,9}(?: [A-Z&][A-Z0-9&/.\-]{0,9}){0,2}"
    r" -?[A-Z]{0,3}[0-9]{1,4}(?:\.[0-9]{1,2})?(?:[A-Z+\-][A-Z0-9+\-]{0,3})?(?: [A-Z]{1,2})?"
    r"(?![A-Z0-9])"
)
KEY_SCAN_RE = re.compile(r"[0-9]{1,4}/[0-9]{1,4}/to/[0-9]{1,4}/(?:Major|Department)/[^\s,.;:)]+")
```

Checks, in order, all violations collected:

1. Every `CODE_SCAN_RE` match in the letter must be in the allowed course-code set after `normalize_course_code`-style whitespace collapsing (uppercase, collapse runs of spaces); a match that fails even that collapse is a violation quoting the raw token.
2. Every `KEY_SCAN_RE` match must be in the allowed agreement-key set.
3. Completeness: every selected finding with at least one of `student_course_codes` or `receiving_course_code` must be addressed, meaning at least one of those codes appears in the letter (word-boundary match, defined below); an unaddressed finding is a violation naming its position and codes.

Word-boundary match for a known code: `re.search(r"(?<![A-Z0-9])" + re.escape(code) + r"(?![A-Z0-9])", letter_text)`.

Recorded trade-off: `CODE_SCAN_RE` will flag benign uppercase-plus-number tokens (a "GPA 3.8" the model slipped in) as violations.
That costs one repair round; the alternative costs an invented citation surviving into a letter a student mails.
The system prompt's no-abbreviation rule keeps the false-positive rate low, and the safety direction is deliberate.

## `compute_cited`

`compute_cited(letter_text: str, bundle: dict) -> list[CitedCourse]`.
For each selected finding in ascending position order, for each code in its `student_course_codes` in stored order: append `CitedCourse(course_code=code, finding_position=position)` when the word-boundary match finds the code in the letter.
No deduplication across findings: a course serving two selected findings yields two entries, and the wire order above is the locked tie-break the UI consumes.

## The template letter (`render_template_letter`)

`render_template_letter(bundle) -> str`, pure and deterministic; the fallback path is `letter_text = render_template_letter(bundle)` and `cited = compute_cited(letter_text, bundle)`.
Locked text, findings in ascending position order, paragraphs joined by blank lines:

Opening:

```
Dear Transfer Credit Evaluator,

I am writing to request a review of several courses I completed at {sending_institution}, as part of my application to the {major} program at {receiving_institution}. The {year_label} ASSIST articulation agreement for this pair supports the requests below.
```

Per finding, choosing the first matching row:

| Condition | Paragraph |
| --- | --- |
| `code == "no_articulation"` | `The agreement lists no articulation for {codes}. I respectfully request an individual review of this coursework for transfer credit, and I can provide the official course outline of record on request.` |
| `code == "unresolved"` | `My records also include coursework ({codes}) that could not be matched against the college's current course list. I can provide documentation to resolve it.` |
| otherwise (an at-risk finding with a citation) | `I ask that {codes} be reviewed toward {target}{detail_clause} (agreement {assist_key}, {citation.year_label}).` |

Where `{codes}` joins `student_course_codes` with `", "` and a final `" and "` for two or more; `{target}` is `receiving_course_code`, else `receiving_course_title`, else `the articulated requirement`; `{detail_clause}` is `"; the evaluation noted: {detail}"` when `detail` is present, else empty.
An `unresolved` finding with empty `student_course_codes` renders `my records` in place of the parenthesized codes.

Closing:

```
Thank you for your time and consideration.

Sincerely,
[Your name]
```

A test asserts `validate_citations(render_template_letter(bundle), bundle)` passes on the demo-shape fixture, so the fallback can never be rejected by the validator it bypasses.

## The node service (`write_petition`)

```python
write_petition(
    *,
    petition_id: str,
    evaluation: Evaluation,
    finding_positions: Sequence[int],
    sending_name: str,
    receiving_name: str,
    major_label: str,
    engine: GenerationEngine[PetitionDraft],
    clock: Clock,
) -> Petition
```

Flow, locked:

1. `bundle = build_findings_bundle(...)`; `user_prompt = build_user_prompt(bundle)`.
2. `draft = engine.generate(run_id=petition_id, system=PETITION_WRITER_SYSTEM, user_prompt=user_prompt, post_validate=lambda d: validate_citations(d.letter_text, bundle))`.
3. Success: `Petition(status="succeeded", fallback=False, reason_code=None, letter_text=draft.letter_text, cited=compute_cited(draft.letter_text, bundle), ...)`.
4. `GenerationError` with `reason_code == LlmReasonCode.REPAIR_LIMIT_EXCEEDED`: the template fallback, `status="succeeded"`, `fallback=True`, that reason code, template letter and its `cited`.
5. Any other `GenerationError`: `status="failed"`, its reason code, letter null, cited empty.
6. `created_at = clock.now()`; the function never raises.

The engine is constructed by the caller (N3, tests) with `node_name="petition_writer"`, `PetitionDraft`, and `PETITION_WRITER_CONFIG` (locked in `00-overview.md` decision 2).

## Tests (`backend/tests/llm/test_petition_writer.py`)

Build inputs from `backend/tests/fixtures/valid/evaluation/demo_shape.json` (it carries one finding per code, so at-risk, no-articulation, and unresolved paragraphs are all reachable) via the existing `Harness` seams in `backend/tests/llm/conftest.py` (frozen clock, sequential ids, real `SqliteCallLogStore`).

| Test | Pins |
| --- | --- |
| happy path | Valid draft citing only allowed codes -> `succeeded`, `fallback` false, `cited` matches the letter, one `pass` log row under `run_id == petition_id`. |
| invented code repairs then succeeds | Script: draft citing `CS 999`, then a clean draft; asserts one `schema_rejected` row, the repair suffix quotes `CS 999`, `requests[1]["user_prompt"] == requests[0]["user_prompt"]` (cache-stability), final `succeeded`. |
| invented agreement key is a violation | Same shape with a fabricated `KEY_SCAN_RE` token. |
| unaddressed finding is a violation | Draft omitting one selected finding's codes; the violation names the position. |
| repair exhaustion falls back | Three rejected drafts -> `succeeded`, `fallback` true, `reason_code == repair_limit_exceeded`, `letter_text == render_template_letter(bundle)`, three `schema_rejected` rows. |
| refusal fails | `refusal()` script -> `failed`, `reason_code == refusal`. |
| non-retryable transport fails | Scripted auth `TransportError` -> `failed`, `reason_code == auth_failed`, one zero-token log row. |
| template letter is self-consistent | `validate_citations(render_template_letter(bundle), bundle)` raises nothing; template `cited` covers every selected finding with codes. |
| unselected findings stay out | Place the sentinel string `UNSELECTED-FINDING-MARKER-XY 999` in an unselected finding's `detail`; assert it appears in neither `user_prompt` nor the allowed vocabulary. |
| bundle determinism | `build_user_prompt(bundle)` is byte-identical across two builds from the same evaluation. |
| prompt pin, layer 2 | `capture_prompt_frames` with (invented-code draft, clean draft); `assert_prompt_pin` with the computed sha256, `must_contain=[PETITION_WRITER_SYSTEM, "FINDINGS OBJECT (canonical JSON"]`, `must_exclude=[the sentinel above]`. |

Layer-1 pin: add the `PromptPin("PETITION_WRITER_SYSTEM", ..., "petition-writer-v1", "<sha256>")` row; the executor computes the hash by running the test once and copying the reported value, per the harness's failure message.
No test asserts prose wording outside the two pin tests.

## Gates

`make check` green (includes the new fixtures, schema regeneration, and `mypy --strict` on the new modules); no network anywhere; no new dependencies.
