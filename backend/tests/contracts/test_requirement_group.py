import pytest
from pydantic import ValidationError

from starmap.common.ids import sha256_hex
from starmap.contracts.requirement_group import RequirementGroup
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "requirement_group"))
INVALID = list(iter_fixtures("invalid", "requirement_group"))


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse_and_ids_derive(case: FixtureCase) -> None:
    group = RequirementGroup.model_validate(case.payload)
    derived = "rg_" + sha256_hex(f"{group.major_id}\n{group.name}")[:16]
    assert group.requirement_group_id == derived


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        RequirementGroup.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def test_model_is_frozen() -> None:
    group = RequirementGroup.model_validate(VALID[0].payload)
    with pytest.raises(ValidationError):
        group.name = "mutated"


def test_unknown_field_rejected() -> None:
    payload = dict(VALID[0].payload) | {"unexpected_field": 1}
    with pytest.raises(ValidationError, match="unexpected_field"):
        RequirementGroup.model_validate(payload)
