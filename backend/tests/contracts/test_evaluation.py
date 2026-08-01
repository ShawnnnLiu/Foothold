import pytest
from pydantic import ValidationError

from starmap.contracts.evaluation import (
    CODES_FORBIDDING_CITATION,
    CODES_REQUIRING_CITATION,
    Citation,
    Evaluation,
    Finding,
)
from starmap.contracts.reason_codes import BUCKET_FOR_CODE, EvaluationFindingCode, TriageBucket
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "evaluation"))
INVALID = list(iter_fixtures("invalid", "evaluation"))

CITATION = {
    "assist_key": "76/113/to/7/Major/d2dfb7a8-d505-4e70-f33c-08ddd3b241a4",
    "position": 5,
    "year_label": "2025-2026",
}


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse(case: FixtureCase) -> None:
    assert Evaluation.model_validate(case.payload).evaluation_id.startswith("eval_")


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Evaluation.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def valid_payload(stem: str) -> dict[str, object]:
    (case,) = [case for case in VALID if case.path.stem == stem]
    assert isinstance(case.payload, dict)
    return dict(case.payload)


def finding_payload(code: EvaluationFindingCode) -> dict[str, object]:
    """The smallest legal finding for a code, per the citation partition."""
    payload: dict[str, object] = {
        "code": code.value,
        "bucket": BUCKET_FOR_CODE[code].value,
        "student_course_codes": ["MATH 1A"],
        "units": 5.0,
    }
    if code in CODES_REQUIRING_CITATION:
        payload["citation"] = dict(CITATION)
    if code is EvaluationFindingCode.ADVISEMENT_NOTE:
        payload["advisements"] = ["Advisement text the student must read."]
    return payload


def test_model_is_frozen() -> None:
    evaluation = Evaluation.model_validate(valid_payload("minimal"))
    with pytest.raises(ValidationError):
        evaluation.year_id = 75


def test_nested_models_are_frozen() -> None:
    evaluation = Evaluation.model_validate(valid_payload("minimal"))
    with pytest.raises(ValidationError):
        evaluation.findings[0].units = 1.0
    with pytest.raises(ValidationError):
        evaluation.units.clean_units = 1.0


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError, match="unexpected_field"):
        Evaluation.model_validate(valid_payload("minimal") | {"unexpected_field": 1})


def test_unknown_finding_field_rejected() -> None:
    """`extra="forbid"` on `Finding` is what makes a confidence score or a
    free-text LLM field structurally impossible in the petition vocabulary."""
    with pytest.raises(ValidationError, match="confidence"):
        Finding.model_validate(
            finding_payload(EvaluationFindingCode.TRANSFERS_CLEAN) | {"confidence": 0.9}
        )


def test_optional_collections_default_to_empty_rather_than_null() -> None:
    evaluation = Evaluation.model_validate(valid_payload("minimal"))
    assert evaluation.dept_keys == []
    assert evaluation.findings[0].advisements == []
    assert evaluation.findings[0].detail is None
    assert evaluation.units.at_risk_dollars is None, "no cost row means None, never 0.0"


def test_citation_partition_is_total_and_disjoint() -> None:
    """A new finding code cannot ship without a decision about whether it points
    at a published articulation; this test is what forces that decision."""
    assert not CODES_REQUIRING_CITATION & CODES_FORBIDDING_CITATION
    assert set(EvaluationFindingCode) == CODES_REQUIRING_CITATION | CODES_FORBIDDING_CITATION


@pytest.mark.parametrize("code", list(EvaluationFindingCode), ids=lambda code: code.value)
def test_every_code_has_a_legal_finding_and_rejects_every_other_bucket(
    code: EvaluationFindingCode,
) -> None:
    payload = finding_payload(code)
    assert Finding.model_validate(payload).bucket is BUCKET_FOR_CODE[code]
    for bucket in TriageBucket:
        if bucket is BUCKET_FOR_CODE[code]:
            continue
        with pytest.raises(ValidationError, match="does not match code"):
            Finding.model_validate(payload | {"bucket": bucket.value})


@pytest.mark.parametrize("code", sorted(CODES_REQUIRING_CITATION), ids=lambda code: code.value)
def test_codes_claiming_an_articulation_cannot_drop_their_citation(
    code: EvaluationFindingCode,
) -> None:
    with pytest.raises(ValidationError, match="citation is required"):
        Finding.model_validate(finding_payload(code) | {"citation": None})


@pytest.mark.parametrize("code", sorted(CODES_FORBIDDING_CITATION), ids=lambda code: code.value)
def test_codes_citing_nothing_cannot_carry_a_citation(code: EvaluationFindingCode) -> None:
    with pytest.raises(ValidationError, match="citation must be null"):
        Finding.model_validate(finding_payload(code) | {"citation": dict(CITATION)})


def test_demo_shape_covers_every_finding_code() -> None:
    """The reference shape for the increment-6 evaluator and the Week 2 petition
    citation validator: if a code has no example here, neither consumer has one."""
    evaluation = Evaluation.model_validate(valid_payload("demo_shape"))
    assert {finding.code for finding in evaluation.findings} == set(EvaluationFindingCode)


def test_demo_shape_is_laid_out_in_evaluator_order() -> None:
    """Order is deliberately not contract-enforced (doc 03 owns the sort key),
    so the reference fixture is where the intended order is pinned."""
    bucket_rank = {
        TriageBucket.TRANSFERS_CLEAN: 0,
        TriageBucket.AT_RISK: 1,
        TriageBucket.NO_ARTICULATION: 2,
        TriageBucket.STILL_OWED: 3,
    }
    evaluation = Evaluation.model_validate(valid_payload("demo_shape"))
    keys = [
        (
            bucket_rank[finding.bucket],
            finding.code.value,
            finding.receiving_course_code or "",
            finding.student_course_codes[0] if finding.student_course_codes else "",
        )
        for finding in evaluation.findings
    ]
    assert keys == sorted(keys)


def test_unresolved_findings_name_courses_outside_the_student_course_list() -> None:
    """Unresolved input never becomes a `StudentCourse`, so a finding's course
    codes are deliberately not a subset of `student_courses`; a subset validator
    would delete the one finding the student most needs to see."""
    evaluation = Evaluation.model_validate(valid_payload("demo_shape"))
    resolved = {course.course_code for course in evaluation.student_courses}
    (unresolved,) = [
        finding
        for finding in evaluation.findings
        if finding.code is EvaluationFindingCode.UNRESOLVED
    ]
    assert unresolved.student_course_codes
    assert not set(unresolved.student_course_codes) & resolved


def test_stale_year_citation_may_predate_the_evaluation_year() -> None:
    """The citation names the year of the agreement actually evaluated, which is
    the whole point of `stale_year`; pinning it to the envelope year would make
    the finding uncheckable."""
    evaluation = Evaluation.model_validate(valid_payload("demo_shape"))
    (stale,) = [
        finding
        for finding in evaluation.findings
        if finding.code is EvaluationFindingCode.STALE_YEAR
    ]
    assert stale.citation is not None
    assert stale.citation.year_label != evaluation.year_label


def test_citation_year_label_shares_the_agreement_consecutive_years_rule() -> None:
    with pytest.raises(ValidationError, match="spans non-consecutive years"):
        Citation.model_validate(dict(CITATION) | {"year_label": "2025-2030"})


def test_student_course_codes_are_normalized_then_checked_for_duplicates() -> None:
    payload = valid_payload("minimal")
    findings = payload["findings"]
    assert isinstance(findings, list)
    finding = dict(findings[0]) | {"student_course_codes": ["  math 1a ", "MATH 1B"]}
    parsed = Finding.model_validate(finding)
    assert parsed.student_course_codes == ["MATH 1A", "MATH 1B"]
