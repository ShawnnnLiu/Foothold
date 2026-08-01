import pytest
from pydantic import ValidationError

from starmap.contracts.agreement import (
    Agreement,
    RequirementGroupAsset,
    derive_agreement_id,
)
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "agreement"))
INVALID = list(iter_fixtures("invalid", "agreement"))

# The template-asset models get their own fixture directory: `RequirementGroupAsset`
# is not reachable through an `Agreement` payload (the envelope holds no template
# field), so the harness cannot validate those fixtures with `Agreement`.
VALID_GROUPS = list(iter_fixtures("valid", "requirement_group_asset"))
INVALID_GROUPS = list(iter_fixtures("invalid", "requirement_group_asset"))


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse(case: FixtureCase) -> None:
    agreement = Agreement.model_validate(case.payload)
    assert agreement.agreement_id == derive_agreement_id(agreement.assist_key)


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Agreement.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


@pytest.mark.parametrize("case", VALID_GROUPS, ids=fixture_ids)
def test_valid_group_fixtures_parse(case: FixtureCase) -> None:
    assert RequirementGroupAsset.model_validate(case.payload).sections


@pytest.mark.parametrize("case", INVALID_GROUPS, ids=fixture_ids)
def test_invalid_group_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        RequirementGroupAsset.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def valid_payload(stem: str) -> dict[str, object]:
    (case,) = [case for case in VALID if case.path.stem == stem]
    assert isinstance(case.payload, dict)
    return dict(case.payload)


def group_payload(stem: str) -> dict[str, object]:
    (case,) = [case for case in VALID_GROUPS if case.path.stem == stem]
    assert isinstance(case.payload, dict)
    return dict(case.payload)


def test_model_is_frozen() -> None:
    agreement = Agreement.model_validate(valid_payload("major_cse_cs"))
    with pytest.raises(ValidationError):
        agreement.label = "Physics B.S."


def test_group_model_is_frozen() -> None:
    group = RequirementGroupAsset.model_validate(group_payload("cse15l_or_cse29"))
    with pytest.raises(ValidationError):
        group.conjunction = "And"


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError, match="unexpected_field"):
        Agreement.model_validate(valid_payload("major_cse_cs") | {"unexpected_field": 1})


def test_unknown_group_field_rejected() -> None:
    with pytest.raises(ValidationError, match="unexpected_field"):
        RequirementGroupAsset.model_validate(
            group_payload("cse15l_or_cse29") | {"unexpected_field": 1}
        )


def test_both_observed_key_formats_parse() -> None:
    major = Agreement.model_validate(valid_payload("major_cse_cs"))
    dept = Agreement.model_validate(valid_payload("dept_math"))
    assert major.assist_key.split("/")[4] == "Major"
    assert dept.assist_key.split("/")[4] == "Department"
    assert (major.category, dept.category) == ("major", "dept")


def test_derived_id_is_a_pure_function_of_the_key() -> None:
    key = "76/113/to/7/Department/8952"
    assert derive_agreement_id(key) == derive_agreement_id(key)
    assert derive_agreement_id(key) != derive_agreement_id("76/113/to/7/Department/8953")


def test_sending_department_keys_are_out_of_scope() -> None:
    """The report lists carry mirror-direction `SendingDepartment` keys; v1
    neither fetches nor models them, so the pattern must exclude them."""
    key = "76/113/to/7/SendingDepartment/9040"
    payload = valid_payload("dept_math") | {
        "assist_key": key,
        "agreement_id": derive_agreement_id(key),
    }
    with pytest.raises(ValidationError, match="assist_key"):
        Agreement.model_validate(payload)


def test_publish_date_is_kept_verbatim_with_seven_fractional_digits() -> None:
    agreement = Agreement.model_validate(valid_payload("major_cse_cs"))
    assert agreement.publish_date == "2026-06-08T23:04:32.5510019"


def test_group_conjunction_comes_from_the_capture() -> None:
    choice = RequirementGroupAsset.model_validate(group_payload("cse15l_or_cse29"))
    required = RequirementGroupAsset.model_validate(group_payload("math_requirements"))
    assert (choice.conjunction, required.conjunction) == ("Or", "And")


def test_cell_ids_are_unique_within_a_group() -> None:
    group = RequirementGroupAsset.model_validate(group_payload("math_requirements"))
    cell_ids = [cell.cell_id for section in group.sections for cell in section.cells]
    assert len(cell_ids) == len(set(cell_ids))
