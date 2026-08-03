"""The deterministic transfer evaluator (implementation plan doc 03, as amended 2026-08-02).

Pure functions from (resolved student courses, stored agreements) to a typed
`Evaluation`. No LLM, no network, no wall clock: `created_at` comes from the
injected `Clock` and `evaluation_id` from the injected `IdGenerator`, so two
runs over the same inputs differ only in those two injected values.

The semantics are locked in doc 03 plus its 2026-08-02 amendment; the load
bearing ones, restated where the code enforces them:

- A `note` leaf never satisfies anything and never counts toward course
  arithmetic; notes downgrade a satisfied match to at-risk and are always
  surfaced on the finding (axiom).
- A `partial` outcome contributes nothing to requirement satisfaction: not to
  section completion, not to a `select_courses` pool.
- A series receiving side is one unit: its finding carries no single course
  code, `receiving_course_title` quotes ASSIST's own series name verbatim.
- An owed group's advisements ride its still-owed finding; a satisfied group's
  advisements are deferred to the Week 2 board rendering (amendment).
- Every finding that claims a published articulation carries its citation
  (`assist_key`, `position`, `year_label`).

`evaluate_pair` never sees unresolved input; `build_evaluation` resolves
requests against the `cc_courses` vocabulary first (doc 03 step 6) and turns
misses into `unresolved` findings. Requests are assumed to carry normalized
course codes; `Finding` validation rejects anything else by construction.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

from starmap.common.clock import Clock
from starmap.common.ids import IdGenerator
from starmap.contracts.agreement import Agreement, RequirementGroupAsset, TemplateCell
from starmap.contracts.articulation import Articulation, ReceivingCourse, ReceivingSeries
from starmap.contracts.articulation_expr import AllOf, AnyOf, ArticulationExpr, CourseLeaf
from starmap.contracts.evaluation import Citation, Evaluation, Finding, StudentCourse, UnitsSummary
from starmap.contracts.reason_codes import BUCKET_FOR_CODE, EvaluationFindingCode, TriageBucket
from starmap.transfer.costs import CostTable

ExprState = Literal["satisfied", "partial", "unsatisfied"]

# `AnyOf` picks the best child by state; ties break on the earliest list index.
_STATE_RANK: dict[ExprState, int] = {"satisfied": 0, "partial": 1, "unsatisfied": 2}

# The locked finding order (doc 03 step 8); the view-model preserves it.
BUCKET_RANK: dict[TriageBucket, int] = {
    TriageBucket.TRANSFERS_CLEAN: 0,
    TriageBucket.AT_RISK: 1,
    TriageBucket.NO_ARTICULATION: 2,
    TriageBucket.STILL_OWED: 3,
}

# Deterministic cap for detail enumerations (amendment): pools run 2 to 33
# cells in the corridor and `Finding.detail` caps at 500 characters, so the
# cap is applied by count, never by character length.
MAX_DETAIL_ENTRIES = 8


@dataclass(frozen=True, slots=True)
class ExprOutcome:
    """One expression evaluation: state, the codes used, the codes that would
    complete the path, and the note texts encountered on the evaluated path."""

    state: ExprState
    matched: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DeptAgreement:
    agreement: Agreement
    articulations: tuple[Articulation, ...]


@dataclass(frozen=True, slots=True)
class AgreementBundle:
    """Everything one evaluation reads, assembled by the composition root.

    `dept_agreements` must arrive sorted by `assist_key` and every articulation
    list by `position` (the store reads already are); `latest_year_id` is the
    derived `MAX(academic_year_id)` for the pair and `latest_year_label` its
    label, both supplied by the root because the evaluator opens no database.
    """

    major: Agreement
    major_articulations: tuple[Articulation, ...]
    requirement_groups: tuple[RequirementGroupAsset, ...]
    dept_agreements: tuple[DeptAgreement, ...]
    latest_year_id: int
    latest_year_label: str


@dataclass(frozen=True, slots=True)
class CourseRequest:
    """One requested course, before resolution against the vocabulary.

    `units` may be None only for a course that fails resolution (its
    `unresolved` finding then carries 0); a resolved course needs real units.
    """

    course_code: str
    units: float | None = None
    title: str | None = None
    resolution: Literal["exact", "fuzzy_match"] = "exact"


# --- expression evaluation ----------------------------------------------------


def evaluate_expr(expr: ArticulationExpr, courses: frozenset[str]) -> ExprOutcome:
    """Locked semantics, doc 03: leaves as stated; `all` over course-bearing
    children; `any` picks the best child and reports that branch alone."""
    if isinstance(expr, CourseLeaf):
        if expr.course in courses:
            return ExprOutcome("satisfied", matched=(expr.course,))
        return ExprOutcome("unsatisfied", missing=(expr.course,))
    if isinstance(expr, AllOf):
        return _all_outcome(expr.all, [evaluate_expr(child, courses) for child in expr.all])
    if isinstance(expr, AnyOf):
        return _any_outcome([evaluate_expr(child, courses) for child in expr.any])
    return ExprOutcome("unsatisfied", notes=(expr.note,))


def _has_course_leaf(expr: ArticulationExpr) -> bool:
    if isinstance(expr, CourseLeaf):
        return True
    if isinstance(expr, AllOf):
        return any(_has_course_leaf(child) for child in expr.all)
    if isinstance(expr, AnyOf):
        return any(_has_course_leaf(child) for child in expr.any)
    return False


def _all_outcome(
    children: Sequence[ArticulationExpr], outcomes: Sequence[ExprOutcome]
) -> ExprOutcome:
    """Course-bearing children decide the state; notes come from EVERY child,
    because every branch of an `all` is required context. The all-notes group
    (the "note-only articulation" edge) has no course-bearing child and stays
    unsatisfied."""
    bearing = [
        outcome
        for child, outcome in zip(children, outcomes, strict=True)
        if _has_course_leaf(child)
    ]
    if bearing and all(outcome.state == "satisfied" for outcome in bearing):
        state: ExprState = "satisfied"
    elif any(outcome.state in ("satisfied", "partial") for outcome in bearing):
        state = "partial"
    else:
        state = "unsatisfied"
    return ExprOutcome(
        state,
        matched=_union(outcome.matched for outcome in bearing),
        missing=_union(outcome.missing for outcome in bearing),
        notes=tuple(note for outcome in outcomes for note in outcome.notes),
    )


def _any_outcome(outcomes: Sequence[ExprOutcome]) -> ExprOutcome:
    """The chosen child's outcome only; unchosen branches contribute nothing."""
    best_index = min(range(len(outcomes)), key=lambda i: (_STATE_RANK[outcomes[i].state], i))
    return outcomes[best_index]


def _union(groups: Iterable[tuple[str, ...]]) -> tuple[str, ...]:
    return tuple(sorted({code for group in groups for code in group}))


# --- classification -----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Evaluated:
    """One evaluated articulation, kept for the coverage, double-use, and
    still-owed passes."""

    agreement: Agreement
    articulation: Articulation
    outcome: ExprOutcome


def evaluate_pair(
    student_courses: Sequence[StudentCourse], bundle: AgreementBundle
) -> list[Finding]:
    """Doc 03's locked classification, in order, over all bundle agreements."""
    courses = frozenset(course.course_code for course in student_courses)
    resolution = {course.course_code: course.resolution for course in student_courses}
    units = {course.course_code: course.units for course in student_courses}

    evaluated = [
        _Evaluated(agreement, articulation, evaluate_expr(articulation.sending_expr, courses))
        for agreement, articulations in _agreements_in_order(bundle)
        for articulation in articulations
        if articulation.sending_expr is not None
    ]

    findings: list[Finding] = []
    for entry in evaluated:
        finding = _classify(entry, bundle, resolution, units)
        if finding is not None:
            findings.append(finding)
    findings.extend(_uncovered(evaluated, student_courses))
    findings.extend(_double_use(evaluated, units))
    findings.extend(_still_owed(evaluated, bundle))
    return sort_findings(findings)


def _agreements_in_order(
    bundle: AgreementBundle,
) -> list[tuple[Agreement, tuple[Articulation, ...]]]:
    return [
        (bundle.major, bundle.major_articulations),
        *((dept.agreement, dept.articulations) for dept in bundle.dept_agreements),
    ]


def _classify(
    entry: _Evaluated,
    bundle: AgreementBundle,
    resolution: dict[str, Literal["exact", "fuzzy_match"]],
    units: dict[str, float],
) -> Finding | None:
    """At most one finding per articulation outcome (doc 03 step 3)."""
    outcome = entry.outcome
    if outcome.state == "unsatisfied":
        return None

    advisements = [*entry.articulation.advisements, *outcome.notes]
    matched_units = sum(units[code] for code in outcome.matched)
    receiving_code, receiving_title = _receiving_of(entry.articulation)
    citation = Citation(
        assist_key=entry.agreement.assist_key,
        position=entry.articulation.position,
        year_label=entry.agreement.academic_year_label,
    )

    if outcome.state == "partial":
        detail = f"matched {', '.join(outcome.matched)}; missing {', '.join(outcome.missing)}"
        return _finding(
            EvaluationFindingCode.PARTIAL_SERIES,
            student_course_codes=list(outcome.matched),
            receiving_course_code=receiving_code,
            receiving_course_title=receiving_title,
            units=matched_units,
            citation=citation,
            advisements=advisements,
            detail=detail,
        )

    fuzzy = sorted(code for code in outcome.matched if resolution[code] == "fuzzy_match")
    stale = entry.agreement.academic_year_id < bundle.latest_year_id
    if advisements:
        code = EvaluationFindingCode.ADVISEMENT_NOTE
    elif fuzzy:
        code = EvaluationFindingCode.FUZZY_MATCH
    elif stale:
        code = EvaluationFindingCode.STALE_YEAR
    else:
        code = EvaluationFindingCode.TRANSFERS_CLEAN

    detail_parts = []
    if fuzzy:
        detail_parts.append(f"fuzzy-matched input: {', '.join(fuzzy)}")
    if stale:
        detail_parts.append(
            f"agreement year {entry.agreement.academic_year_label} predates the latest "
            f"published year {bundle.latest_year_label}"
        )
    return _finding(
        code,
        student_course_codes=list(outcome.matched),
        receiving_course_code=receiving_code,
        receiving_course_title=receiving_title,
        units=matched_units,
        citation=citation,
        advisements=advisements,
        detail="; ".join(detail_parts) or None,
    )


def _receiving_of(articulation: Articulation) -> tuple[str | None, str | None]:
    """A series has no single code; its title is ASSIST's own series name
    (amendment), so the UI and the petition letter quote the agreement."""
    if articulation.receiving_course is not None:
        return articulation.receiving_course.course_code, articulation.receiving_course.title
    assert articulation.receiving_series is not None  # the contract requires exactly one
    return None, articulation.receiving_series.name


def _uncovered(
    evaluated: Sequence[_Evaluated], student_courses: Sequence[StudentCourse]
) -> list[Finding]:
    """Doc 03 step 4: a course no satisfied or partial articulation used."""
    covered = {
        code
        for entry in evaluated
        if entry.outcome.state in ("satisfied", "partial")
        for code in entry.outcome.matched
    }
    return [
        _finding(
            EvaluationFindingCode.NO_ARTICULATION,
            student_course_codes=[course.course_code],
            units=course.units,
        )
        for course in student_courses
        if course.course_code not in covered
    ]


def _double_use(evaluated: Sequence[_Evaluated], units: dict[str, float]) -> list[Finding]:
    """Doc 03 step 5: a course matched by two or more satisfied articulations
    where at least one carries notes or advisements, cited at the first."""
    findings = []
    for code in sorted(units):
        involved = [
            entry
            for entry in evaluated
            if entry.outcome.state == "satisfied" and code in entry.outcome.matched
        ]
        if len(involved) < 2:
            continue
        if not any(entry.articulation.advisements or entry.outcome.notes for entry in involved):
            continue
        first = involved[0]
        labels = [
            f"{entry.agreement.assist_key}:{entry.articulation.position}" for entry in involved
        ]
        findings.append(
            _finding(
                EvaluationFindingCode.DOUBLE_COUNT_RISK,
                student_course_codes=[code],
                units=units[code],
                citation=Citation(
                    assist_key=first.agreement.assist_key,
                    position=first.articulation.position,
                    year_label=first.agreement.academic_year_label,
                ),
                detail=_enumerate(labels, ", ", "and {n} more"),
            )
        )
    return findings


# --- still-owed (doc 03 step 7, amended for series cells and select_courses) --


def _still_owed(evaluated: Sequence[_Evaluated], bundle: AgreementBundle) -> list[Finding]:
    satisfied_cells = {
        entry.articulation.template_cell_id
        for entry in evaluated
        if entry.articulation.template_cell_id is not None and entry.outcome.state == "satisfied"
    }
    cited_cells: dict[str, int] = {}
    for articulation in bundle.major_articulations:
        if articulation.template_cell_id is not None:
            cited_cells.setdefault(articulation.template_cell_id, articulation.position)
    findings = []
    for group in bundle.requirement_groups:
        finding = _group_finding(group, satisfied_cells, cited_cells, bundle.major)
        if finding is not None:
            findings.append(finding)
    return findings


def _group_finding(
    group: RequirementGroupAsset,
    satisfied_cells: set[str],
    cited_cells: dict[str, int],
    major: Agreement,
) -> Finding | None:
    """One finding per unsatisfied group; a cell is satisfied only by a
    `satisfied` expression (partial contributes nothing, amendment)."""

    def satisfied(cell: TemplateCell) -> bool:
        return cell.cell_id in satisfied_cells

    all_cells = [cell for section in group.sections for cell in section.cells]
    owed_cells = [cell for cell in all_cells if not satisfied(cell)]

    detail: str | None
    if group.select_courses is not None:
        satisfied_count = len(all_cells) - len(owed_cells)
        remaining = group.select_courses - satisfied_count
        if remaining <= 0:
            return None
        cheapest = sorted(range(len(owed_cells)), key=lambda i: (_cell_units(owed_cells[i]), i))
        owed_units = sum(_cell_units(owed_cells[i]) for i in cheapest[:remaining])
        labels = [_cell_label(cell) for cell in owed_cells]
        detail = f"complete {remaining} more from: " + _enumerate(
            labels, " or ", "{n} more options"
        )
    elif group.conjunction == "And":
        if not owed_cells:
            return None
        owed_units = sum(_cell_units(cell) for cell in owed_cells)
        detail = _enumerate([_cell_label(cell) for cell in owed_cells], " and ", "{n} more")
    else:
        section_owed = [
            [cell for cell in section.cells if not satisfied(cell)] for section in group.sections
        ]
        if any(not owed for owed in section_owed):
            return None
        owed_units = min(sum(_cell_units(cell) for cell in owed) for owed in section_owed)
        detail = _enumerate([_cell_label(cell) for cell in owed_cells], " or ", "{n} more")

    receiving_code: str | None = None
    receiving_title: str | None = None
    if len(owed_cells) == 1:
        cell = owed_cells[0]
        if cell.course is not None:
            receiving_code, receiving_title = cell.course.course_code, cell.course.title
        elif cell.series is not None:
            receiving_title = cell.series.name
        if group.select_courses is None:
            detail = None
    position = next(
        (cited_cells[cell.cell_id] for cell in owed_cells if cell.cell_id in cited_cells), 0
    )
    return _finding(
        EvaluationFindingCode.STILL_OWED,
        receiving_course_code=receiving_code,
        receiving_course_title=receiving_title,
        units=owed_units,
        citation=Citation(
            assist_key=major.assist_key, position=position, year_label=major.academic_year_label
        ),
        advisements=list(group.advisements),
        detail=detail,
    )


def receiving_units(course: ReceivingCourse | None, series: ReceivingSeries | None) -> float:
    """The one receiving-side units accounting, shared with `arbitrage.py`.

    Series units: sum for `And`, minimum for `Or` (the cheapest honest
    completion, amendment); a course is its own `units_min`."""
    if course is not None:
        return course.units_min
    assert series is not None  # the contracts require exactly one
    course_units = [item.units_min for item in series.courses]
    return min(course_units) if series.conjunction == "Or" else sum(course_units)


def _cell_units(cell: TemplateCell) -> float:
    return receiving_units(cell.course, cell.series)


def _cell_label(cell: TemplateCell) -> str:
    if cell.course is not None:
        return cell.course.course_code
    assert cell.series is not None  # the contract requires exactly one
    return cell.series.name


def _enumerate(labels: Sequence[str], joiner: str, more_template: str) -> str:
    """The locked cap: at most `MAX_DETAIL_ENTRIES` labels, then a count."""
    if len(labels) <= MAX_DETAIL_ENTRIES:
        return joiner.join(labels)
    shown = joiner.join(labels[:MAX_DETAIL_ENTRIES])
    return shown + joiner + more_template.format(n=len(labels) - MAX_DETAIL_ENTRIES)


# --- assembly -----------------------------------------------------------------


def sort_findings(findings: Sequence[Finding]) -> list[Finding]:
    """The locked key; the sort must stay stable so equal keys preserve
    evaluation order (amendment)."""
    return sorted(
        findings,
        key=lambda finding: (
            BUCKET_RANK[finding.bucket],
            finding.code.value,
            finding.receiving_course_code or "",
            finding.student_course_codes[0] if finding.student_course_codes else "",
        ),
    )


def build_evaluation(
    *,
    requests: Sequence[CourseRequest],
    vocabulary: frozenset[str],
    bundle: AgreementBundle,
    id_generator: IdGenerator,
    clock: Clock,
    cost_table: CostTable | None = None,
) -> Evaluation:
    """Resolve requests against the `cc_courses` vocabulary (doc 03 step 6),
    evaluate, and assemble the contract object. Without a cost table (or a
    target row in it) the dollar fields stay None, the honest "we do not
    know"."""
    student_courses: list[StudentCourse] = []
    unresolved: list[Finding] = []
    for request in requests:
        if request.course_code not in vocabulary:
            unresolved.append(
                _finding(
                    EvaluationFindingCode.UNRESOLVED,
                    student_course_codes=[request.course_code],
                    units=request.units if request.units is not None else 0.0,
                )
            )
            continue
        if request.units is None:
            raise ValueError(f"resolved course {request.course_code!r} carries no units")
        student_courses.append(
            StudentCourse(
                course_code=request.course_code,
                title=request.title,
                units=request.units,
                resolution=request.resolution,
            )
        )
    findings = sort_findings([*evaluate_pair(student_courses, bundle), *unresolved])
    target_rate = (
        cost_table.target_rate(bundle.major.receiving_institution_id)
        if cost_table is not None
        else None
    )
    return Evaluation(
        evaluation_id=id_generator.new_id("eval"),
        sending_institution_id=bundle.major.sending_institution_id,
        receiving_institution_id=bundle.major.receiving_institution_id,
        major_key=bundle.major.assist_key,
        dept_keys=[dept.agreement.assist_key for dept in bundle.dept_agreements],
        year_id=bundle.latest_year_id,
        year_label=bundle.latest_year_label,
        student_courses=student_courses,
        findings=findings,
        units=units_summary(student_courses, findings, target_rate=target_rate),
        created_at=clock.now(),
    )


def units_summary(
    student_courses: Sequence[StudentCourse],
    findings: Sequence[Finding],
    target_rate: float | None = None,
) -> UnitsSummary:
    """Doc 03 units attribution: each student course counts in exactly one
    bucket, decided by its first covering finding in bucket-rank order. The
    dollar fields are the locked formula `units * target_per_unit[receiving]`
    rounded to 2 places; without a target rate both stay None."""
    totals = {TriageBucket.TRANSFERS_CLEAN: 0.0, TriageBucket.AT_RISK: 0.0}
    for course in student_courses:
        best = next(
            (
                finding
                for finding in findings
                if course.course_code in finding.student_course_codes
                and finding.code is not EvaluationFindingCode.UNRESOLVED
            ),
            None,
        )
        if best is not None and best.bucket in totals:
            totals[best.bucket] += course.units
    no_articulation_units = sum(
        finding.units
        for finding in findings
        if finding.code is EvaluationFindingCode.NO_ARTICULATION
    )
    return UnitsSummary(
        clean_units=totals[TriageBucket.TRANSFERS_CLEAN],
        at_risk_units=totals[TriageBucket.AT_RISK],
        no_articulation_units=no_articulation_units,
        still_owed_units=sum(
            finding.units
            for finding in findings
            if finding.code is EvaluationFindingCode.STILL_OWED
        ),
        at_risk_dollars=_dollars(totals[TriageBucket.AT_RISK], target_rate),
        no_articulation_dollars=_dollars(no_articulation_units, target_rate),
    )


def _dollars(units: float, target_rate: float | None) -> float | None:
    """The locked doc 03 formula; None (not zero) when the rate is unknown."""
    if target_rate is None:
        return None
    return round(units * target_rate, 2)


def _finding(
    code: EvaluationFindingCode,
    *,
    student_course_codes: list[str] | None = None,
    receiving_course_code: str | None = None,
    receiving_course_title: str | None = None,
    units: float,
    citation: Citation | None = None,
    advisements: list[str] | None = None,
    detail: str | None = None,
) -> Finding:
    """The single construction site, so `bucket` can never disagree with
    `BUCKET_FOR_CODE` at the call sites."""
    return Finding(
        code=code,
        bucket=BUCKET_FOR_CODE[code],
        student_course_codes=student_course_codes or [],
        receiving_course_code=receiving_course_code,
        receiving_course_title=receiving_course_title,
        units=units,
        citation=citation,
        advisements=advisements or [],
        detail=detail,
    )
