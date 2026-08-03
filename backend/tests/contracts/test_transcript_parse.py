import pytest
from pydantic import ValidationError

from starmap.contracts.transcript_parse import TranscriptParse, TranscriptProposal
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures


def is_proposal(case: FixtureCase) -> bool:
    """`proposal_*` fixtures validate against `TranscriptProposal` (spec, Fixtures)."""
    return case.path.stem.startswith("proposal_")


ALL_VALID = list(iter_fixtures("valid", "transcript_parse"))
ALL_INVALID = list(iter_fixtures("invalid", "transcript_parse"))
VALID_PARSES = [case for case in ALL_VALID if not is_proposal(case)]
VALID_PROPOSALS = [case for case in ALL_VALID if is_proposal(case)]
INVALID_PARSES = [case for case in ALL_INVALID if not is_proposal(case)]
INVALID_PROPOSALS = [case for case in ALL_INVALID if is_proposal(case)]


@pytest.mark.parametrize("case", VALID_PARSES, ids=fixture_ids)
def test_valid_parse_fixtures_parse(case: FixtureCase) -> None:
    parse = TranscriptParse.model_validate(case.payload)
    assert parse.created_at.utcoffset() is not None


@pytest.mark.parametrize("case", VALID_PROPOSALS, ids=fixture_ids)
def test_valid_proposal_fixtures_parse(case: FixtureCase) -> None:
    proposal = TranscriptProposal.model_validate(case.payload)
    for course in proposal.courses:
        assert course.course_code is not None or course.title is not None


@pytest.mark.parametrize("case", INVALID_PARSES, ids=fixture_ids)
def test_invalid_parse_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        TranscriptParse.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


@pytest.mark.parametrize("case", INVALID_PROPOSALS, ids=fixture_ids)
def test_invalid_proposal_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        TranscriptProposal.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def test_fixture_names_cover_the_spec_lists() -> None:
    """The spec's locked fixture names all exist; a rename cannot slip through."""
    assert {case.path.stem for case in ALL_VALID} == {
        "pending",
        "succeeded_mixed",
        "succeeded_empty",
        "failed",
        "proposal_minimal",
    }
    assert len(ALL_INVALID) == 19


def test_succeeded_with_both_lists_empty_is_legal() -> None:
    empty = next(case for case in VALID_PARSES if case.path.stem == "succeeded_empty")
    parse = TranscriptParse.model_validate(empty.payload)
    assert parse.status == "succeeded"
    assert parse.chips == []
    assert parse.unresolved == []


def test_parse_is_frozen() -> None:
    parse = TranscriptParse.model_validate(VALID_PARSES[0].payload)
    with pytest.raises(ValidationError):
        parse.status = "failed"


def test_proposal_is_frozen() -> None:
    proposal = TranscriptProposal.model_validate(VALID_PROPOSALS[0].payload)
    with pytest.raises(ValidationError):
        proposal.courses = []


def test_unknown_field_rejected() -> None:
    payload = dict(VALID_PARSES[0].payload) | {"unexpected_field": 1}
    with pytest.raises(ValidationError, match="unexpected_field"):
        TranscriptParse.model_validate(payload)


def test_chip_course_codes_are_normalized() -> None:
    mixed = next(case.payload for case in VALID_PARSES if case.path.stem == "succeeded_mixed")
    payload = dict(mixed)
    payload["chips"] = [dict(payload["chips"][0]) | {"course_code": "  math   1a "}]
    parse = TranscriptParse.model_validate(payload)
    assert parse.chips[0].course_code == "MATH 1A"


def test_proposed_course_codes_are_not_normalized() -> None:
    """The model copies the transcript verbatim; resolution tolerates the shape."""
    proposal = TranscriptProposal.model_validate({"courses": [{"course_code": "Math-20A"}]})
    assert proposal.courses[0].course_code == "Math-20A"
