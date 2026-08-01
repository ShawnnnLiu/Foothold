import pytest
from pydantic import ValidationError

from starmap.contracts.offering import Offering
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "offering"))
INVALID = list(iter_fixtures("invalid", "offering"))


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse(case: FixtureCase) -> None:
    offering = Offering.model_validate(case.payload)
    assert offering.term == case.payload["term"]


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Offering.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def test_model_is_frozen() -> None:
    offering = Offering.model_validate(VALID[0].payload)
    with pytest.raises(ValidationError):
        offering.year = 2030


def test_unknown_field_rejected() -> None:
    payload = dict(VALID[0].payload) | {"unexpected_field": 1}
    with pytest.raises(ValidationError, match="unexpected_field"):
        Offering.model_validate(payload)
