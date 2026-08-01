import pytest
from pydantic import ValidationError

from starmap.contracts.institution import Institution
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "institution"))
INVALID = list(iter_fixtures("invalid", "institution"))


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse(case: FixtureCase) -> None:
    assert Institution.model_validate(case.payload).assist_id > 0


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Institution.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def valid_payload(stem: str) -> dict[str, object]:
    (case,) = [case for case in VALID if case.path.stem == stem]
    assert isinstance(case.payload, dict)
    return dict(case.payload)


def test_model_is_frozen() -> None:
    institution = Institution.model_validate(valid_payload("de_anza"))
    with pytest.raises(ValidationError):
        institution.name = "Foothill College"


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError, match="unexpected_field"):
        Institution.model_validate(valid_payload("de_anza") | {"unexpected_field": 1})


def test_the_three_corridor_kinds_are_all_covered_by_valid_fixtures() -> None:
    kinds = {Institution.model_validate(case.payload).kind for case in VALID}
    assert kinds == {"cc", "uc", "csu"}


def test_padded_payload_code_is_rejected_so_normalization_cannot_be_skipped() -> None:
    """ASSIST pads codes (`"DAC     "`); accepting the padding would let one
    institution exist under two spellings."""
    with pytest.raises(ValidationError, match="code"):
        Institution.model_validate(valid_payload("de_anza") | {"code": "DAC     "})
