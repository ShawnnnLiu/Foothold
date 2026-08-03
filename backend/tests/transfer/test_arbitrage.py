"""Mode B engine tests (frontend doc 04), fixture-driven against the transfer
scenario bundles so the candidate semantics stay pinned to the same data the
evaluator is pinned to."""

from datetime import UTC, datetime
from typing import Any

from starmap.contracts.evaluation import Evaluation
from starmap.transfer.arbitrage import build_arbitrage
from starmap.transfer.costs import CostTable
from starmap.transfer.evaluate import AgreementBundle, build_evaluation
from tests.support.clocks import FrozenClock
from tests.support.ids import SequentialIdGenerator
from tests.transfer.scenarios import (
    SCENARIO_DIR,
    build_bundle,
    build_requests,
    load_scenario,
    vocabulary_of,
)

CLOCK_START = datetime(2026, 8, 3, tzinfo=UTC)

# Mirrors the curated table's real UCSD margin: 291 - 46 = 245 per unit.
UCSD_RATE = 291.0
CC_RATE = 46.0


def cost_table(rates: dict[str, float]) -> CostTable:
    return CostTable.model_validate(
        {
            "version": "costs-v1",
            "sources": [
                {
                    "url": "https://example.test/costs",
                    "note": "engine-test fixture rates",
                    "retrieved": "2026-08-03",
                }
            ],
            "cc_per_unit_default": CC_RATE,
            "target_per_unit": rates,
        }
    )


UCSD_TABLE = cost_table({"7": UCSD_RATE})


def evaluate_scenario(
    name: str, requests: list[dict[str, Any]] | None = None
) -> tuple[Evaluation, AgreementBundle]:
    """The scenario's evaluation through the full `build_evaluation` path;
    `requests` overrides the scenario's own students (vocabulary follows)."""
    scenario = load_scenario(SCENARIO_DIR / f"{name}.json")
    raw_requests = scenario["requests"] if requests is None else requests
    vocabulary = (
        vocabulary_of(scenario)
        if requests is None
        else frozenset(entry["course_code"] for entry in raw_requests)
    )
    bundle = build_bundle(scenario["bundle"])
    evaluation = build_evaluation(
        requests=build_requests(raw_requests),
        vocabulary=vocabulary,
        bundle=bundle,
        id_generator=SequentialIdGenerator(),
        clock=FrozenClock(CLOCK_START),
    )
    return evaluation, bundle


def test_untouched_articulation_becomes_a_row() -> None:
    """`still_owed`: CIS 22A satisfies position 0, so the untouched CIS 22C
    -> CSE 12 articulation is the one candidate."""
    evaluation, bundle = evaluate_scenario("still_owed")
    rows, omitted = build_arbitrage(evaluation, bundle, UCSD_TABLE)
    assert omitted == 0
    (row,) = rows
    assert row.missing_course_codes == ["CIS 22C"]
    assert row.receiving_course_code == "CSE 12"
    assert row.receiving_series_name is None
    assert row.units == 4.0
    assert row.savings_dollars == round(4.0 * (UCSD_RATE - CC_RATE), 2)
    assert row.citation.assist_key == bundle.major.assist_key
    assert row.citation.position == 1
    assert row.citation.year_label == bundle.major.academic_year_label


def test_partial_series_emits_only_the_missing_member() -> None:
    """`partial_series`: MATH 1C is done, so the row sells MATH 1D alone at
    the receiving cell's units, not the whole pair."""
    evaluation, bundle = evaluate_scenario("partial_series")
    rows, omitted = build_arbitrage(evaluation, bundle, UCSD_TABLE)
    assert omitted == 0
    (row,) = rows
    assert row.missing_course_codes == ["MATH 1D"]
    assert row.receiving_course_code == "MATH 20E"
    assert row.units == 4.0
    assert row.savings_dollars == round(4.0 * (UCSD_RATE - CC_RATE), 2)


def test_partial_series_receiving_side_keeps_the_series_name() -> None:
    """`series_receiving` with only PHYS 4A taken: the row quotes ASSIST's
    series name verbatim, carries no single course code, and sums the And
    series units (the same accounting the evaluator uses)."""
    evaluation, bundle = evaluate_scenario(
        "series_receiving",
        requests=[{"course_code": "PHYS 4A", "units": 5.0, "resolution": "exact"}],
    )
    rows, _ = build_arbitrage(evaluation, bundle, UCSD_TABLE)
    (row,) = rows
    assert row.missing_course_codes == ["PHYS 4B"]
    assert row.receiving_course_code is None
    assert row.receiving_course_title is None
    assert row.receiving_series_name == "PHYSICS 2A, PHYSICS 2B"
    assert row.units == 8.0
    assert row.savings_dollars == round(8.0 * (UCSD_RATE - CC_RATE), 2)


def test_note_only_articulation_is_skipped() -> None:
    """An all-notes expression has no course leaves: nothing purchasable."""
    evaluation, bundle = evaluate_scenario("note_only_articulation")
    assert build_arbitrage(evaluation, bundle, UCSD_TABLE) == ([], 0)


def test_no_articulation_cell_is_skipped() -> None:
    """A null `sending_expr` (No Course Articulated) is not a candidate."""
    evaluation, bundle = evaluate_scenario("no_course_articulated_cell")
    assert build_arbitrage(evaluation, bundle, UCSD_TABLE) == ([], 0)


def test_satisfied_articulations_produce_no_rows() -> None:
    evaluation, bundle = evaluate_scenario("transfers_clean")
    assert build_arbitrage(evaluation, bundle, UCSD_TABLE) == ([], 0)


def test_none_rate_target_yields_none_dollars_and_counts_them() -> None:
    """A target with no per-unit rate: every row keeps `savings_dollars`
    None (never zero), stays in the list, and is counted, never dropped."""
    evaluation, bundle = evaluate_scenario("select_courses_pool")
    rows, omitted = build_arbitrage(evaluation, bundle, cost_table({"11": 305.0}))
    assert len(rows) == 2
    assert omitted == 2
    assert all(row.savings_dollars is None for row in rows)


def test_absent_cost_table_behaves_like_a_missing_rate() -> None:
    evaluation, bundle = evaluate_scenario("select_courses_pool")
    rows, omitted = build_arbitrage(evaluation, bundle, None)
    assert omitted == len(rows) == 2
    assert all(row.savings_dollars is None for row in rows)


def test_dollar_rows_order_by_savings_descending_then_position() -> None:
    """`select_courses_pool`: CHEM 6C (5 units, position 2) outranks CHEM 6B
    (4 units, position 1) on savings despite the later position."""
    evaluation, bundle = evaluate_scenario("select_courses_pool")
    rows, _ = build_arbitrage(evaluation, bundle, UCSD_TABLE)
    assert [row.receiving_course_code for row in rows] == ["CHEM 6C", "CHEM 6B"]
    assert [row.savings_dollars for row in rows] == [1225.0, 980.0]


def test_equal_savings_tie_breaks_on_position() -> None:
    """`still_owed` with a course that matches nothing: both 4-unit
    candidates save the same, so articulation position orders them."""
    evaluation, bundle = evaluate_scenario(
        "still_owed", requests=[{"course_code": "MATH 1A", "units": 5.0, "resolution": "exact"}]
    )
    rows, _ = build_arbitrage(evaluation, bundle, UCSD_TABLE)
    assert [row.receiving_course_code for row in rows] == ["CSE 8A", "CSE 12"]
    assert [row.citation.position for row in rows] == [0, 1]


def test_unrankable_rows_sort_after_dollar_rows_by_position() -> None:
    """The None-after-dollars half of the locked sort key. One evaluation has
    one target and therefore one margin, so a mixed list cannot arise through
    the public API; the observable pin is that unrankable rows still order
    deterministically by position."""
    evaluation, bundle = evaluate_scenario("select_courses_pool")
    rows, _ = build_arbitrage(evaluation, bundle, None)
    assert [row.receiving_course_code for row in rows] == ["CHEM 6B", "CHEM 6C"]
    assert [row.citation.position for row in rows] == [1, 2]


def test_purity_same_inputs_equal_outputs() -> None:
    evaluation, bundle = evaluate_scenario("select_courses_pool")
    first = build_arbitrage(evaluation, bundle, UCSD_TABLE)
    second = build_arbitrage(evaluation, bundle, UCSD_TABLE)
    assert first == second
