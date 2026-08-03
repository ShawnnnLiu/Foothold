"""Direct unit tests for `evaluate_expr` (mandatory per the testing strategy):
every leaf and group state case, partial-series arithmetic, note collection on
`all` against chosen-branch-only on `any`, determinism, and the committed
`articulation_expr` valid fixtures."""

from starmap.contracts.articulation_expr import (
    AllOf,
    AnyOf,
    ArticulationExpr,
    CourseLeaf,
    NoteLeaf,
    parse_articulation_expr,
)
from starmap.transfer.evaluate import ExprOutcome, evaluate_expr
from tests.support.fixtures import iter_fixtures


def expr(data: object) -> ArticulationExpr:
    parsed = parse_articulation_expr(data)
    assert isinstance(parsed, AllOf | AnyOf | CourseLeaf | NoteLeaf)
    return parsed


def test_course_leaf_satisfied() -> None:
    assert evaluate_expr(expr({"course": "MATH 1A"}), frozenset({"MATH 1A"})) == ExprOutcome(
        "satisfied", matched=("MATH 1A",)
    )


def test_course_leaf_unsatisfied_names_the_missing_course() -> None:
    assert evaluate_expr(expr({"course": "MATH 1A"}), frozenset()) == ExprOutcome(
        "unsatisfied", missing=("MATH 1A",)
    )


def test_note_leaf_never_satisfies_and_never_counts() -> None:
    outcome = evaluate_expr(expr({"note": "See adviser"}), frozenset({"MATH 1A"}))
    assert outcome == ExprOutcome("unsatisfied", notes=("See adviser",))


def test_all_satisfied_unions_matched() -> None:
    tree = expr({"all": [{"course": "MATH 1C"}, {"course": "MATH 1D"}]})
    outcome = evaluate_expr(tree, frozenset({"MATH 1C", "MATH 1D"}))
    assert outcome == ExprOutcome("satisfied", matched=("MATH 1C", "MATH 1D"))


def test_all_partial_names_matched_and_missing() -> None:
    tree = expr({"all": [{"course": "MATH 1C"}, {"course": "MATH 1D"}]})
    outcome = evaluate_expr(tree, frozenset({"MATH 1C"}))
    assert outcome == ExprOutcome("partial", matched=("MATH 1C",), missing=("MATH 1D",))


def test_all_unsatisfied_when_no_child_matches() -> None:
    tree = expr({"all": [{"course": "MATH 1C"}, {"course": "MATH 1D"}]})
    outcome = evaluate_expr(tree, frozenset({"PHYS 4A"}))
    assert outcome.state == "unsatisfied"
    assert outcome.missing == ("MATH 1C", "MATH 1D")


def test_all_notes_group_stays_unsatisfied() -> None:
    """The note-only articulation edge: no course-bearing child, never satisfied."""
    tree = expr({"all": [{"note": "See department"}]})
    outcome = evaluate_expr(tree, frozenset({"MATH 1A"}))
    assert outcome == ExprOutcome("unsatisfied", notes=("See department",))


def test_all_collects_notes_from_every_child() -> None:
    tree = expr(
        {
            "all": [
                {"course": "MATH 1A"},
                {"note": "first note"},
                {"any": [{"course": "MATH 2A"}, {"note": "branch note"}]},
            ]
        }
    )
    outcome = evaluate_expr(tree, frozenset({"MATH 1A", "MATH 2A"}))
    assert outcome.state == "satisfied"
    assert outcome.notes == ("first note",)


def test_lone_course_with_note_is_satisfied_but_keeps_the_note() -> None:
    tree = expr({"all": [{"course": "MATH 1A"}, {"note": "Minimum grade required: C or better"}]})
    outcome = evaluate_expr(tree, frozenset({"MATH 1A"}))
    assert outcome.state == "satisfied"
    assert outcome.matched == ("MATH 1A",)
    assert outcome.notes == ("Minimum grade required: C or better",)


def test_any_picks_the_best_state() -> None:
    tree = expr(
        {
            "any": [
                {"all": [{"course": "MATH 1C"}, {"course": "MATH 1D"}]},
                {"course": "MATH 2A"},
            ]
        }
    )
    outcome = evaluate_expr(tree, frozenset({"MATH 1C", "MATH 2A"}))
    assert outcome == ExprOutcome("satisfied", matched=("MATH 2A",))


def test_any_tie_breaks_on_the_earliest_index() -> None:
    tree = expr({"any": [{"course": "MATH 2A"}, {"course": "MATH 2AH"}]})
    outcome = evaluate_expr(tree, frozenset({"MATH 2A", "MATH 2AH"}))
    assert outcome.matched == ("MATH 2A",)


def test_any_reports_only_the_chosen_branch() -> None:
    """Unchosen branches contribute nothing, notes included."""
    tree = expr(
        {
            "any": [
                {"course": "MATH 2A"},
                {"all": [{"course": "MATH 2AH"}, {"note": "honors note"}]},
            ]
        }
    )
    outcome = evaluate_expr(tree, frozenset({"MATH 2A", "MATH 2AH"}))
    assert outcome == ExprOutcome("satisfied", matched=("MATH 2A",))


def test_any_of_all_unsatisfied_keeps_first_branch() -> None:
    tree = expr({"any": [{"course": "MATH 1C"}, {"course": "MATH 1D"}]})
    outcome = evaluate_expr(tree, frozenset())
    assert outcome == ExprOutcome("unsatisfied", missing=("MATH 1C",))


def _course_codes(tree: ArticulationExpr) -> set[str]:
    if isinstance(tree, CourseLeaf):
        return {tree.course}
    if isinstance(tree, AllOf):
        return {code for child in tree.all for code in _course_codes(child)}
    if isinstance(tree, AnyOf):
        return {code for child in tree.any for code in _course_codes(child)}
    return set()


def test_valid_fixture_trees_evaluate_deterministically() -> None:
    """Every committed articulation_expr fixture, including the depth-3 tree:
    two calls deep-equal, full course set satisfies unless the tree is
    note-only, empty course set never satisfies."""
    for case in iter_fixtures("valid", "articulation_expr"):
        tree = expr(case.payload)
        codes = frozenset(_course_codes(tree))
        full = evaluate_expr(tree, codes)
        assert full == evaluate_expr(tree, codes)
        if codes:
            assert full.state == "satisfied"
        else:
            assert full.state == "unsatisfied"
        assert evaluate_expr(tree, frozenset()).state != "satisfied"
