"""Mode B arbitrage: the articulation index inverted (frontend doc 04).

`build_arbitrage` is a pure function from a validated `Evaluation` and its
`AgreementBundle` to the ranked "take it at a community college instead"
rows: no clock, no ids, no I/O, no LLM anywhere.

Candidacy is recomputed with `evaluate_expr` over the evaluation's resolved
course set, never parsed out of findings text, so the engine and the
evaluator can never disagree about what "satisfied" means. The candidate set
is the major agreement's articulations whose sending expression is not fully
satisfied, which yields both flavors the prototype shows: untouched
articulations and partial series completions.
"""

from starmap.contracts.arbitrage import ArbitrageRow
from starmap.contracts.evaluation import Citation, Evaluation
from starmap.transfer.costs import CostTable
from starmap.transfer.evaluate import AgreementBundle, evaluate_expr, receiving_units


def build_arbitrage(
    evaluation: Evaluation, bundle: AgreementBundle, cost_table: CostTable | None
) -> tuple[list[ArbitrageRow], int]:
    """The ranked rows plus the count of rows with no savings figure; such
    rows are surfaced after all dollar rows, never silently dropped."""
    courses = frozenset(course.course_code for course in evaluation.student_courses)
    margin: float | None = None
    if cost_table is not None:
        target_rate = cost_table.target_rate(evaluation.receiving_institution_id)
        if target_rate is not None:
            margin = target_rate - cost_table.cc_per_unit_default

    ranked: list[tuple[bool, float, int, ArbitrageRow]] = []
    for articulation in bundle.major_articulations:
        if articulation.sending_expr is None:
            continue
        outcome = evaluate_expr(articulation.sending_expr, courses)
        if outcome.state == "satisfied":
            continue
        if not outcome.missing:
            # Note-only expressions (and any all-notes path): nothing purchasable.
            continue
        units = receiving_units(articulation.receiving_course, articulation.receiving_series)
        savings = None if margin is None else round(units * margin, 2)
        course = articulation.receiving_course
        row = ArbitrageRow(
            missing_course_codes=list(outcome.missing),
            receiving_course_code=course.course_code if course is not None else None,
            receiving_course_title=course.title if course is not None else None,
            receiving_series_name=(
                articulation.receiving_series.name
                if articulation.receiving_series is not None
                else None
            ),
            units=units,
            savings_dollars=savings,
            citation=Citation(
                assist_key=bundle.major.assist_key,
                position=articulation.position,
                year_label=bundle.major.academic_year_label,
            ),
        )
        ranked.append((savings is None, -(savings or 0.0), articulation.position, row))

    ranked.sort(key=lambda entry: entry[:3])
    rows = [row for *_, row in ranked]
    return rows, sum(1 for row in rows if row.savings_dollars is None)
