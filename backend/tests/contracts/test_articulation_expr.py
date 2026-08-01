import json

import pytest
from pydantic import ValidationError

from starmap.contracts.articulation_expr import (
    AllOf,
    AnyOf,
    ArticulationExprRoot,
    CourseLeaf,
    NoteLeaf,
    expr_depth,
    parse_articulation_expr,
)
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "articulation_expr"))
INVALID = list(iter_fixtures("invalid", "articulation_expr"))


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse(case: FixtureCase) -> None:
    expr = ArticulationExprRoot.model_validate(case.payload).root
    assert isinstance(expr, AllOf | AnyOf | CourseLeaf | NoteLeaf)


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        ArticulationExprRoot.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def test_model_is_frozen() -> None:
    leaf = CourseLeaf.model_validate({"course": "MATH 1A"})
    with pytest.raises(ValidationError):
        leaf.course = "MATH 1B"


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError, match="unexpected_field"):
        CourseLeaf.model_validate({"course": "MATH 1A", "unexpected_field": 1})


def plan_example_payload() -> object:
    (case,) = [case for case in VALID if case.path.stem == "plan_example"]
    return case.payload


def test_plan_example_round_trips_verbatim() -> None:
    payload = plan_example_payload()
    root = ArticulationExprRoot.model_validate(payload)
    assert root.model_dump(mode="json", exclude_defaults=True) == payload


def test_round_trip_through_json_is_stable() -> None:
    root = ArticulationExprRoot.model_validate(plan_example_payload())
    reparsed = ArticulationExprRoot.model_validate(json.loads(root.model_dump_json()))
    assert reparsed == root


def test_parse_articulation_expr_dispatches_by_key() -> None:
    assert isinstance(parse_articulation_expr({"course": "MATH 1A"}), CourseLeaf)
    assert isinstance(parse_articulation_expr({"note": "must complete entire series"}), NoteLeaf)
    assert isinstance(parse_articulation_expr({"all": [{"course": "MATH 1A"}]}), AllOf)
    assert isinstance(parse_articulation_expr({"any": [{"course": "MATH 1A"}]}), AnyOf)


def test_parse_articulation_expr_passes_instances_through() -> None:
    leaf = CourseLeaf.model_validate({"course": "MATH 1A"})
    assert parse_articulation_expr(leaf) is leaf


def test_parse_articulation_expr_rejects_non_mappings() -> None:
    with pytest.raises(ValueError, match="must be a mapping"):
        parse_articulation_expr(["MATH 1A"])


def test_expr_depth_counts_group_levels() -> None:
    leaf = CourseLeaf.model_validate({"course": "MATH 1A"})
    assert expr_depth(leaf) == 1
    group = AnyOf.model_validate({"any": [{"course": "MATH 1A"}]})
    assert expr_depth(group) == 2
    nested = AllOf.model_validate({"all": [{"any": [{"course": "MATH 1A"}]}]})
    assert expr_depth(nested) == 3
