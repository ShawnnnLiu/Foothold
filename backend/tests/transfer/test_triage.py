"""The triage board: a pure projection of the evaluation, order-preserving,
with header totals equal to the units summary."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from starmap.contracts.reason_codes import TriageBucket
from starmap.transfer.costs import CostTable
from starmap.transfer.evaluate import build_evaluation
from starmap.transfer.triage import CREDIT_BUCKETS, build_triage_board
from tests.support.clocks import FrozenClock
from tests.support.ids import SequentialIdGenerator
from tests.transfer.scenarios import (
    SCENARIO_DIR,
    build_bundle,
    build_requests,
    load_scenario,
    scenario_paths,
    vocabulary_of,
)
from tests.transfer.test_costs import table_payload


def evaluation_for(name: str, *, cost_table: CostTable | None = None):  # type: ignore[no-untyped-def]
    scenario = load_scenario(SCENARIO_DIR / f"{name}.json")
    return build_evaluation(
        requests=build_requests(scenario["requests"]),
        vocabulary=vocabulary_of(scenario),
        bundle=build_bundle(scenario["bundle"]),
        id_generator=SequentialIdGenerator(),
        clock=FrozenClock(datetime(2026, 8, 2, tzinfo=UTC)),
        cost_table=cost_table,
    )


def test_build_triage_board_is_pure() -> None:
    evaluation = evaluation_for("double_count_risk")
    assert build_triage_board(evaluation) == build_triage_board(evaluation)


@pytest.mark.parametrize("path", scenario_paths(), ids=lambda path: path.stem)
def test_board_partitions_findings_in_evaluator_order(path: Path) -> None:
    """Concatenating the columns and the owed list in bucket-rank order must
    reproduce the evaluator's findings list exactly: nothing re-sorted,
    nothing dropped, nothing duplicated."""
    scenario = load_scenario(path)
    evaluation = build_evaluation(
        requests=build_requests(scenario["requests"]),
        vocabulary=vocabulary_of(scenario),
        bundle=build_bundle(scenario["bundle"]),
        id_generator=SequentialIdGenerator(),
        clock=FrozenClock(datetime(2026, 8, 2, tzinfo=UTC)),
    )
    board = build_triage_board(evaluation)
    fanned_out = [finding for bucket in CREDIT_BUCKETS for finding in board.columns[bucket]] + list(
        board.still_owed
    )
    assert fanned_out == list(evaluation.findings)


def test_columns_hold_exactly_the_credit_buckets() -> None:
    board = build_triage_board(evaluation_for("still_owed"))
    assert tuple(board.columns.keys()) == CREDIT_BUCKETS
    assert TriageBucket.STILL_OWED not in board.columns


def test_missing_target_row_leaves_dollars_none() -> None:
    """The scenario pair receives at institution 7; a table with no row for
    it must answer None for both dollar fields, never zero."""
    table = CostTable.model_validate(table_payload(target_per_unit={"39": 396.0}))
    evaluation = evaluation_for("no_articulation", cost_table=table)
    assert evaluation.units.at_risk_dollars is None
    assert evaluation.units.no_articulation_dollars is None


def test_header_totals_equal_the_units_summary() -> None:
    evaluation = evaluation_for(
        "no_articulation", cost_table=CostTable.model_validate(table_payload())
    )
    header = build_triage_board(evaluation).header
    assert header.clean_units == evaluation.units.clean_units
    assert header.at_risk_units == evaluation.units.at_risk_units
    assert header.no_articulation_units == evaluation.units.no_articulation_units
    assert header.still_owed_units == evaluation.units.still_owed_units
    assert header.at_risk_dollars == evaluation.units.at_risk_dollars
    assert header.no_articulation_dollars == evaluation.units.no_articulation_dollars
    assert header.course_count == len(evaluation.student_courses)
    assert header.finding_count == len(evaluation.findings)
