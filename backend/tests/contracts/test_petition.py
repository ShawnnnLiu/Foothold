import pytest
from pydantic import ValidationError

from starmap.contracts.petition import Petition, PetitionDraft
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures


def is_draft(case: FixtureCase) -> bool:
    """`draft_*` fixtures validate against `PetitionDraft` (spec, Fixtures)."""
    return case.path.stem.startswith("draft_")


ALL_VALID = list(iter_fixtures("valid", "petition"))
ALL_INVALID = list(iter_fixtures("invalid", "petition"))
VALID_PETITIONS = [case for case in ALL_VALID if not is_draft(case)]
VALID_DRAFTS = [case for case in ALL_VALID if is_draft(case)]
INVALID_PETITIONS = [case for case in ALL_INVALID if not is_draft(case)]
INVALID_DRAFTS = [case for case in ALL_INVALID if is_draft(case)]


@pytest.mark.parametrize("case", VALID_PETITIONS, ids=fixture_ids)
def test_valid_petition_fixtures_parse(case: FixtureCase) -> None:
    petition = Petition.model_validate(case.payload)
    assert petition.created_at.utcoffset() is not None


@pytest.mark.parametrize("case", VALID_DRAFTS, ids=fixture_ids)
def test_valid_draft_fixtures_parse(case: FixtureCase) -> None:
    draft = PetitionDraft.model_validate(case.payload)
    assert len(draft.letter_text) >= 200


@pytest.mark.parametrize("case", INVALID_PETITIONS, ids=fixture_ids)
def test_invalid_petition_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Petition.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


@pytest.mark.parametrize("case", INVALID_DRAFTS, ids=fixture_ids)
def test_invalid_draft_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        PetitionDraft.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def test_fixture_names_cover_the_spec_lists() -> None:
    """The spec's locked fixture names all exist; a rename cannot slip through."""
    assert {case.path.stem for case in ALL_VALID} == {
        "pending",
        "succeeded",
        "succeeded_fallback",
        "failed",
        "draft_minimal",
    }
    assert len(ALL_INVALID) == 22


def test_petition_is_frozen() -> None:
    petition = Petition.model_validate(VALID_PETITIONS[0].payload)
    with pytest.raises(ValidationError):
        petition.status = "failed"


def test_draft_is_frozen() -> None:
    draft = PetitionDraft.model_validate(VALID_DRAFTS[0].payload)
    with pytest.raises(ValidationError):
        draft.letter_text = "mutated"


def test_unknown_field_rejected() -> None:
    payload = dict(VALID_PETITIONS[0].payload) | {"unexpected_field": 1}
    with pytest.raises(ValidationError, match="unexpected_field"):
        Petition.model_validate(payload)


def test_cited_course_codes_are_normalized() -> None:
    succeeded = next(case.payload for case in VALID_PETITIONS if case.path.stem == "succeeded")
    payload = dict(succeeded)
    payload["cited"] = [{"course_code": "  math   1b ", "finding_position": 1}]
    petition = Petition.model_validate(payload)
    assert petition.cited[0].course_code == "MATH 1B"
