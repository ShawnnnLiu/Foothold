import pytest
from pydantic import ValidationError

from starmap.contracts.cc_course import CcCourse
from starmap.contracts.target_course import TargetCourse
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "target_course"))
INVALID = list(iter_fixtures("invalid", "target_course"))
CC_INVALID = list(iter_fixtures("invalid", "cc_course"))


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse(case: FixtureCase) -> None:
    assert TargetCourse.model_validate(case.payload).institution_id > 0


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        TargetCourse.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def valid_payload(stem: str) -> dict[str, object]:
    (case,) = [case for case in VALID if case.path.stem == stem]
    assert isinstance(case.payload, dict)
    return dict(case.payload)


def test_model_is_frozen() -> None:
    course = TargetCourse.model_validate(valid_payload("math_20d"))
    with pytest.raises(ValidationError):
        course.title = "Vector Calculus"


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError, match="unexpected_field"):
        TargetCourse.model_validate(valid_payload("math_20d") | {"unexpected_field": 1})


def test_shape_matches_cc_course_field_for_field() -> None:
    """The duplication is locked (no contract inheritance), so it needs a guard:
    the two projections must stay identical until someone deliberately diverges
    them, and this is the test that fails when they drift by accident."""
    target = TargetCourse.model_json_schema(mode="serialization")
    cc = CcCourse.model_json_schema(mode="serialization")
    assert target["properties"] == cc["properties"]
    assert target["required"] == cc["required"]


@pytest.mark.parametrize("case", CC_INVALID, ids=fixture_ids)
def test_every_cc_course_violation_is_a_target_course_violation(case: FixtureCase) -> None:
    """The validator half of the parity guard, and the reason this contract
    ships two invalid fixtures instead of eleven: `cc_course`'s inventory proves
    each rule fires, and this asserts the same rules are wired in here."""
    with pytest.raises(ValidationError) as excinfo:
        TargetCourse.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def test_long_receiving_title_is_accepted() -> None:
    course = TargetCourse.model_validate(valid_payload("cse_11"))
    assert course.title.startswith("Introduction to Programming")
    assert len(course.title) < 300
