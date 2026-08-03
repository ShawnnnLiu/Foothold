import pytest
from pydantic import ValidationError

from starmap.contracts.articulation import Articulation, ReceivingCourse
from starmap.contracts.articulation_expr import AnyOf, CourseLeaf, NoteLeaf
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "articulation"))
INVALID = list(iter_fixtures("invalid", "articulation"))


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse(case: FixtureCase) -> None:
    assert Articulation.model_validate(case.payload).position >= 0


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        Articulation.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def valid_payload(stem: str) -> dict[str, object]:
    (case,) = [case for case in VALID if case.path.stem == stem]
    assert isinstance(case.payload, dict)
    return dict(case.payload)


def test_model_is_frozen() -> None:
    articulation = Articulation.model_validate(valid_payload("math20e_and_series"))
    with pytest.raises(ValidationError):
        articulation.position = 9


def test_receiving_course_is_frozen() -> None:
    articulation = Articulation.model_validate(valid_payload("math20e_and_series"))
    assert articulation.receiving_course is not None
    with pytest.raises(ValidationError):
        articulation.receiving_course.title = "Something Else"


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError, match="unexpected_field"):
        Articulation.model_validate(valid_payload("math20e_and_series") | {"unexpected_field": 1})


def test_unknown_receiving_course_field_rejected() -> None:
    payload = valid_payload("math20e_and_series")
    receiving = payload["receiving_course"]
    assert isinstance(receiving, dict)
    receiving = receiving | {"unexpected_field": 1}
    with pytest.raises(ValidationError, match="unexpected_field"):
        Articulation.model_validate(payload | {"receiving_course": receiving})


def test_no_articulation_leaves_the_expression_null() -> None:
    articulation = Articulation.model_validate(valid_payload("math10b_no_articulation"))
    assert articulation.sending_expr is None
    assert articulation.no_articulation_reason is None
    assert articulation.template_cell_id is None, "department agreements have no template"


def test_or_of_two_single_course_groups_parses_as_bare_leaves() -> None:
    articulation = Articulation.model_validate(valid_payload("math20d_honors_or_regular"))
    expr = articulation.sending_expr
    assert isinstance(expr, AnyOf)
    assert [leaf.course for leaf in expr.any if isinstance(leaf, CourseLeaf)] == [
        "MATH 2A",
        "MATH 2AH",
    ]


def test_advisement_note_survives_inside_the_expression() -> None:
    articulation = Articulation.model_validate(valid_payload("synthetic_advisement"))
    expr = articulation.sending_expr
    assert expr is not None and not isinstance(expr, CourseLeaf | NoteLeaf | AnyOf)
    assert any(isinstance(child, NoteLeaf) for child in expr.all)
    assert articulation.advisements, "articulation-level advisement text is carried too"


def test_advisements_default_to_empty_rather_than_null() -> None:
    assert Articulation.model_validate(valid_payload("math20e_and_series")).advisements == []


def test_receiving_course_code_derivation_is_enforced_both_ways() -> None:
    """The derivation is what stops the projection the evaluator, the FTS index,
    and the petition validator share from disagreeing with its payload."""
    fields = {
        "prefix": "CSE",
        "number": "15L",
        "title": "Software Tools and Techniques Laboratory",
        "units_min": 2.0,
        "units_max": 2.0,
    }
    assert ReceivingCourse.model_validate(fields | {"course_code": "CSE 15L"}).course_code == (
        "CSE 15L"
    )
    with pytest.raises(ValidationError, match="does not match prefix"):
        ReceivingCourse.model_validate(fields | {"course_code": "CSE 15"})


def test_course_code_is_normalized_before_the_derivation_check() -> None:
    course = ReceivingCourse.model_validate(
        {
            "course_code": "  math   20d ",
            "prefix": "MATH",
            "number": "20D",
            "title": "Introduction to Differential Equations",
            "units_min": 4.0,
            "units_max": 4.0,
        }
    )
    assert course.course_code == "MATH 20D"


def test_reason_and_expression_are_mutually_exclusive_but_either_may_be_absent() -> None:
    payload = valid_payload("math10b_no_articulation")
    with_reason = Articulation.model_validate(
        payload | {"no_articulation_reason": "No comparable course."}
    )
    assert with_reason.sending_expr is None
