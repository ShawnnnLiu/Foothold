import pytest
from pydantic import ValidationError

from starmap.contracts.arbitrage import ArbitrageRow
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "arbitrage"))
INVALID = list(iter_fixtures("invalid", "arbitrage"))


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse(case: FixtureCase) -> None:
    row = ArbitrageRow.model_validate(case.payload)
    assert row.missing_course_codes


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        ArbitrageRow.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def valid_payload(stem: str) -> dict[str, object]:
    (case,) = [case for case in VALID if case.path.stem == stem]
    assert isinstance(case.payload, dict)
    return dict(case.payload)


def test_model_is_frozen() -> None:
    row = ArbitrageRow.model_validate(valid_payload("dollar_row"))
    with pytest.raises(ValidationError):
        row.units = 1.0


def test_unknown_field_rejected() -> None:
    """`extra="forbid"` keeps a confidence score or free-text LLM field
    structurally impossible in a Mode B row."""
    with pytest.raises(ValidationError, match="confidence"):
        ArbitrageRow.model_validate(valid_payload("dollar_row") | {"confidence": 0.9})


def test_no_rate_row_keeps_savings_null_never_zero() -> None:
    row = ArbitrageRow.model_validate(valid_payload("no_rate_row"))
    assert row.savings_dollars is None, "no per-unit rate means None, never 0.0"


def test_series_row_carries_the_series_name_alone() -> None:
    row = ArbitrageRow.model_validate(valid_payload("series_row"))
    assert row.receiving_series_name
    assert row.receiving_course_code is None
    assert row.receiving_course_title is None


def test_missing_course_codes_are_normalized() -> None:
    payload = valid_payload("dollar_row") | {"missing_course_codes": ["  cis 22a "]}
    assert ArbitrageRow.model_validate(payload).missing_course_codes == ["CIS 22A"]
