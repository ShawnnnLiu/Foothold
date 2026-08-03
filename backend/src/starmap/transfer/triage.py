"""The triage board view-model (doc 03, "transfer/triage.py").

`build_triage_board` is a PURE projection of a validated `Evaluation`: no
re-sorting beyond the evaluator's locked finding order, no PRNG, no clock
(the frontend-determinism axiom; `lib/evaluation.ts` mirrors this shape in
Week 2).

Shape decisions recorded here rather than made silently:

- `columns` holds the three credit buckets (`transfers_clean`, `at_risk`,
  `no_articulation`) and `still_owed` is its own field, because still-owed
  findings describe requirements no student course was applied to, not the
  student's credits; together the four cover every finding exactly once.
- A course articulating in both the major and a dept agreement keeps one
  finding per articulation (doc 03 emits per-articulation by design); the
  board does NOT group them in this increment.
- A SATISFIED group's advisements are still absent from the findings object
  and therefore from this board; their surfacing stays deferred to the Week 2
  board rendering (explicit re-deferral recorded in the doc 03 amendment).
"""

from dataclasses import dataclass

from starmap.contracts.evaluation import Evaluation, Finding
from starmap.contracts.reason_codes import TriageBucket

# The three credit columns, in the evaluator's locked bucket-rank order.
CREDIT_BUCKETS: tuple[TriageBucket, ...] = (
    TriageBucket.TRANSFERS_CLEAN,
    TriageBucket.AT_RISK,
    TriageBucket.NO_ARTICULATION,
)


@dataclass(frozen=True, slots=True)
class TriageHeader:
    """The board's headline totals, copied from the evaluation's summary."""

    clean_units: float
    at_risk_units: float
    no_articulation_units: float
    still_owed_units: float
    at_risk_dollars: float | None
    no_articulation_dollars: float | None
    course_count: int
    finding_count: int


@dataclass(frozen=True, slots=True)
class TriageBoard:
    """Findings fanned out by bucket, each column in evaluator order."""

    columns: dict[TriageBucket, tuple[Finding, ...]]
    still_owed: tuple[Finding, ...]
    header: TriageHeader


def build_triage_board(evaluation: Evaluation) -> TriageBoard:
    """Fan the findings out by bucket, preserving the evaluator's order."""
    by_bucket: dict[TriageBucket, list[Finding]] = {bucket: [] for bucket in TriageBucket}
    for finding in evaluation.findings:
        by_bucket[finding.bucket].append(finding)
    return TriageBoard(
        columns={bucket: tuple(by_bucket[bucket]) for bucket in CREDIT_BUCKETS},
        still_owed=tuple(by_bucket[TriageBucket.STILL_OWED]),
        header=TriageHeader(
            clean_units=evaluation.units.clean_units,
            at_risk_units=evaluation.units.at_risk_units,
            no_articulation_units=evaluation.units.no_articulation_units,
            still_owed_units=evaluation.units.still_owed_units,
            at_risk_dollars=evaluation.units.at_risk_dollars,
            no_articulation_dollars=evaluation.units.no_articulation_dollars,
            course_count=len(evaluation.student_courses),
            finding_count=len(evaluation.findings),
        ),
    )
