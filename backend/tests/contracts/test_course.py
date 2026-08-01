import pytest
from pydantic import ValidationError

from starmap.contracts.course import Course
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "course"))
INVALID = list(iter_fixtures("invalid", "course"))


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse(case: FixtureCase) -> None:
    course = Course.model_validate(case.payload)
    assert course.course_code == case.payload["course_code"]


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Course.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def test_model_is_frozen() -> None:
    course = Course.model_validate(VALID[0].payload)
    with pytest.raises(ValidationError):
        course.title = "mutated"


def test_unknown_field_rejected() -> None:
    payload = dict(VALID[0].payload) | {"unexpected_field": 1}
    with pytest.raises(ValidationError, match="unexpected_field"):
        Course.model_validate(payload)
