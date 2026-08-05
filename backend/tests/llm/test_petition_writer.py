"""The petition-writer node suite (doc 01): FakeTransport only, no network.

Inputs come from the demo-shape evaluation fixture, which carries one finding
per code, so the at-risk, no-articulation, and unresolved template paragraphs
are all reachable. No test asserts prose wording outside the two pin tests.
"""

import json
from typing import Any

import pytest

from starmap.contracts.evaluation import Evaluation
from starmap.contracts.petition import Petition, PetitionDraft
from starmap.contracts.reason_codes import LlmReasonCode
from starmap.llm.engine import GenerationEngine
from starmap.llm.errors import TransportError
from starmap.llm.petition_writer import (
    PETITION_WRITER_CONFIG,
    PETITION_WRITER_SYSTEM,
    allowed_agreement_keys,
    allowed_course_codes,
    build_findings_bundle,
    build_user_prompt,
    compute_cited,
    render_template_letter,
    validate_citations,
    write_petition,
)
from tests.llm.conftest import Harness
from tests.support.fixtures import FIXTURES_ROOT
from tests.support.prompt_pins import assert_prompt_pin, capture_prompt_frames
from tests.support.transports import FakeTransport, refusal, success

PETITION_ID = "pet_0123456789abcdef"
SENDING_NAME = "De Anza College"
RECEIVING_NAME = "University of California, San Diego"
MAJOR_LABEL = "Computer Science"

# Every selectable finding in demo_shape: positions 1-6 are at-risk, 7 is
# no-articulation; 0 (transfers_clean) and 8 (still_owed) are not petitionable.
SELECTED_POSITIONS = [1, 2, 3, 4, 5, 6, 7]

# Planted in an UNSELECTED finding's detail; the rot guards assert it can
# reach neither the prompt nor the citation vocabulary. The token is
# deliberately code-shaped ("MARKER-XY 999" matches CODE_SCAN_RE), so the
# assertion is about selection, not about scannability.
SENTINEL = "UNSELECTED-FINDING-MARKER-XY 999"


def load_evaluation() -> Evaluation:
    payload = json.loads((FIXTURES_ROOT / "valid" / "evaluation" / "demo_shape.json").read_text())
    payload["findings"][0]["detail"] = SENTINEL
    return Evaluation.model_validate(payload)


EVALUATION = load_evaluation()


def bundle_for(positions: list[int]) -> dict[str, Any]:
    return build_findings_bundle(
        EVALUATION,
        positions,
        sending_name=SENDING_NAME,
        receiving_name=RECEIVING_NAME,
        major_label=MAJOR_LABEL,
    )


BUNDLE = bundle_for(SELECTED_POSITIONS)

# The template letter is a known-valid draft, so the happy path scripts it
# rather than hand-maintaining a second letter that cites the same vocabulary.
VALID_LETTER = render_template_letter(BUNDLE)
INVENTED_CODE_LETTER = VALID_LETTER + "\n\nI also completed CS 999 with distinction."
INVENTED_KEY_LETTER = VALID_LETTER + "\n\nSee agreement 999/999/to/999/Major/fabricated."
# Renders every selected finding except position 7, so exactly that finding
# goes unaddressed while every cited token stays inside the allowed vocabulary.
UNADDRESSED_LETTER = render_template_letter(bundle_for([1, 2, 3, 4, 5, 6]))

LAYER2_PINNED_SHA256 = "fd7971a14c9567ccf6cd38fac2e54b3c4856cef6594721864841ad301e2a985d"


def run_node(harness: Harness, transport: FakeTransport) -> Petition:
    engine = GenerationEngine(
        "petition_writer",
        PetitionDraft,
        PETITION_WRITER_CONFIG,
        transport,
        harness.store,
        harness.clock,
        harness.ids,
        harness.raw_sink.append,
        harness.sleeper,
    )
    return write_petition(
        petition_id=PETITION_ID,
        evaluation=EVALUATION,
        finding_positions=SELECTED_POSITIONS,
        sending_name=SENDING_NAME,
        receiving_name=RECEIVING_NAME,
        major_label=MAJOR_LABEL,
        engine=engine,
        clock=harness.clock,
    )


def rows(harness: Harness) -> list[tuple[int, int, str, str | None]]:
    return [
        (
            row.attempt,
            row.sdk_retry,
            row.validation_outcome,
            None if row.reason_code is None else row.reason_code.value,
        )
        for row in harness.store.list_for_run(PETITION_ID)
    ]


def draft(letter_text: str) -> dict[str, str]:
    return {"letter_text": letter_text}


# --- outcomes ---------------------------------------------------------------------


def test_happy_path_succeeds_with_cited_index_and_one_pass_row(harness: Harness) -> None:
    transport = FakeTransport([success(draft(VALID_LETTER))])

    petition = run_node(harness, transport)

    assert petition.status == "succeeded"
    assert petition.fallback is False
    assert petition.reason_code is None
    assert petition.petition_id == PETITION_ID
    assert petition.evaluation_id == EVALUATION.evaluation_id
    assert petition.finding_positions == SELECTED_POSITIONS
    assert petition.letter_text == VALID_LETTER
    assert petition.cited == compute_cited(VALID_LETTER, BUNDLE)
    assert petition.cited, "the demo letter must cite at least one course"
    assert rows(harness) == [(0, 0, "pass", None)]


def test_invented_code_is_repaired_then_succeeds(harness: Harness) -> None:
    transport = FakeTransport([success(draft(INVENTED_CODE_LETTER)), success(draft(VALID_LETTER))])

    petition = run_node(harness, transport)

    assert petition.status == "succeeded"
    assert petition.fallback is False
    assert rows(harness) == [(0, 0, "fail", "schema_rejected"), (1, 0, "pass", None)]
    first, second = transport.requests
    assert "CS 999" in second["repair_suffix"]
    # Cache stability: the base prompt is byte-identical across attempts.
    assert second["user_prompt"] == first["user_prompt"]


def test_invented_agreement_key_is_a_violation(harness: Harness) -> None:
    transport = FakeTransport([success(draft(INVENTED_KEY_LETTER)), success(draft(VALID_LETTER))])

    petition = run_node(harness, transport)

    assert petition.status == "succeeded"
    assert rows(harness) == [(0, 0, "fail", "schema_rejected"), (1, 0, "pass", None)]
    assert "999/999/to/999/Major/fabricated" in transport.requests[1]["repair_suffix"]


def test_unaddressed_finding_is_a_violation_naming_its_position(harness: Harness) -> None:
    transport = FakeTransport([success(draft(UNADDRESSED_LETTER)), success(draft(VALID_LETTER))])

    petition = run_node(harness, transport)

    assert petition.status == "succeeded"
    assert rows(harness) == [(0, 0, "fail", "schema_rejected"), (1, 0, "pass", None)]
    suffix = transport.requests[1]["repair_suffix"]
    assert "position 7" in suffix
    assert "MATH 12" in suffix


def test_repair_exhaustion_falls_back_to_the_template_letter(harness: Harness) -> None:
    transport = FakeTransport([success(draft(INVENTED_CODE_LETTER))] * 3)

    petition = run_node(harness, transport)

    assert petition.status == "succeeded"
    assert petition.fallback is True
    assert petition.reason_code is LlmReasonCode.REPAIR_LIMIT_EXCEEDED
    assert petition.letter_text == render_template_letter(BUNDLE)
    assert petition.cited == compute_cited(render_template_letter(BUNDLE), BUNDLE)
    assert rows(harness) == [
        (0, 0, "fail", "schema_rejected"),
        (1, 0, "fail", "schema_rejected"),
        (2, 0, "fail", "schema_rejected"),
    ]


def test_refusal_fails_with_its_reason_code(harness: Harness) -> None:
    transport = FakeTransport([refusal()])

    petition = run_node(harness, transport)

    assert petition.status == "failed"
    assert petition.reason_code is LlmReasonCode.REFUSAL
    assert petition.fallback is False
    assert petition.letter_text is None
    assert petition.cited == []
    assert rows(harness) == [(0, 0, "fail", "refusal")]


def test_non_retryable_transport_failure_fails_with_one_zero_token_row(
    harness: Harness,
) -> None:
    error = TransportError(
        "AuthenticationError", retryable=False, reason_code=LlmReasonCode.AUTH_FAILED
    )
    transport = FakeTransport([error])

    petition = run_node(harness, transport)

    assert petition.status == "failed"
    assert petition.reason_code is LlmReasonCode.AUTH_FAILED
    (row,) = harness.store.list_for_run(PETITION_ID)
    assert (row.input_tokens, row.output_tokens) == (0, 0)
    assert row.response_hash is None


# --- the vocabulary gate ----------------------------------------------------------


def test_template_letter_is_self_consistent() -> None:
    letter = render_template_letter(BUNDLE)

    validate_citations(letter, BUNDLE)

    cited_positions = {entry.finding_position for entry in compute_cited(letter, BUNDLE)}
    positions_with_codes = {
        finding["position"] for finding in BUNDLE["findings"] if finding["student_course_codes"]
    }
    assert cited_positions == positions_with_codes


def test_unselected_findings_reach_neither_prompt_nor_vocabulary() -> None:
    assert SENTINEL in (EVALUATION.findings[0].detail or "")

    user_prompt = build_user_prompt(BUNDLE)

    assert SENTINEL not in user_prompt
    assert all("MARKER" not in code for code in allowed_course_codes(BUNDLE))
    assert all("999" not in code for code in allowed_course_codes(BUNDLE))
    assert all("999" not in key for key in allowed_agreement_keys(BUNDLE))


def test_bundle_and_prompt_are_deterministic() -> None:
    assert build_user_prompt(bundle_for(SELECTED_POSITIONS)) == build_user_prompt(
        bundle_for(SELECTED_POSITIONS)
    )


# --- prompt pin, layer 2 ----------------------------------------------------------


def test_prompt_frames_match_the_pin(harness: Harness) -> None:
    def run(transport: FakeTransport) -> object:
        return run_node(harness, transport)

    frames = capture_prompt_frames(
        run, [success(draft(INVENTED_CODE_LETTER)), success(draft(VALID_LETTER))]
    )

    assert_prompt_pin(
        frames,
        pinned_sha256=LAYER2_PINNED_SHA256,
        must_contain=[PETITION_WRITER_SYSTEM, "FINDINGS OBJECT (canonical JSON"],
        must_exclude=[SENTINEL],
    )


def test_selecting_a_non_petitionable_finding_is_a_programming_error() -> None:
    with pytest.raises(AssertionError, match="not petitionable"):
        bundle_for([0])
