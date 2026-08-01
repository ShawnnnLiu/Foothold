import pytest
from pydantic import ValidationError

from starmap.contracts.cc_course import CcCourse
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "cc_course"))
INVALID = list(iter_fixtures("invalid", "cc_course"))


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse(case: FixtureCase) -> None:
    assert CcCourse.model_validate(case.payload).institution_id > 0


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        CcCourse.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def valid_payload(stem: str) -> dict[str, object]:
    (case,) = [case for case in VALID if case.path.stem == stem]
    assert isinstance(case.payload, dict)
    return dict(case.payload)


def test_model_is_frozen() -> None:
    course = CcCourse.model_validate(valid_payload("math_1a"))
    with pytest.raises(ValidationError):
        course.title = "Calculus II"


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError, match="unexpected_field"):
        CcCourse.model_validate(valid_payload("math_1a") | {"unexpected_field": 1})


def test_course_code_is_normalized_before_the_derivation_check() -> None:
    """Autocomplete offers what the transcript validator resolves against, so a
    row whose code normalized differently from its own parts would break the
    vocabulary gate rather than just look untidy."""
    course = CcCourse.model_validate(valid_payload("math_1a") | {"course_code": "  math   1a "})
    assert course.course_code == "MATH 1A"


def test_letter_prefixed_honors_number_survives_the_derivation() -> None:
    """STAT C1000H is the shape that forced the ASSIST-derived regex; if the
    derivation rejected it, the projection would silently lose the course."""
    course = CcCourse.model_validate(valid_payload("stat_c1000h"))
    assert (course.prefix, course.number, course.course_code) == ("STAT", "C1000H", "STAT C1000H")


def test_fractional_units_are_preserved_exactly() -> None:
    course = CcCourse.model_validate(valid_payload("cis_22c"))
    assert (course.units_min, course.units_max) == (4.5, 4.5)
