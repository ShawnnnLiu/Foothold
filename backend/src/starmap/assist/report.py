"""The build report: everything the build refused to store, and why.

`data/reports/assist_build_report.json` is committed and deterministic:
`json.dumps(..., indent=2, sort_keys=True) + "\\n"` with NO timestamps anywhere
(fetch dates live in the gitignored cache manifest, which is where a rerun is
allowed to differ). Two builds over one cache produce one byte-identical file.

This is the "no silent drops" axiom made auditable. Every excluded agreement
and every excluded articulation appears here with its typed `AssistBuildCode`,
so reviewing a build means reading one file rather than trusting a summary
line. The `advisement_shape_unknown` total is the specific signal split S9c
acts on: it counts the articulations whose advisements exist in ASSIST but
whose shape this build has never seen.

`report.py` only folds: the walk (`corridor.py`) says what was in scope and the
normalizer says what came out of it, and neither knows about the other.
"""

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from starmap.assist.corridor import CorridorScope, PairScope
from starmap.assist.normalize import Exclusion, NormalizedAgreement
from starmap.contracts.reason_codes import AssistBuildCode

REPORT_INDENT = 2


@dataclass(frozen=True, slots=True)
class PairReport:
    sending_id: int
    receiving_id: int
    year_id: int | None
    major_reports: int
    major_selected: int
    dept_reports: int
    dept_selected: int
    agreements_stored: int
    agreements_excluded: tuple[Exclusion, ...]
    articulations_stored: int
    articulations_excluded: tuple[Exclusion, ...]


@dataclass(frozen=True, slots=True)
class BuildReport:
    targets: tuple[int, ...]
    sending_count: int
    preferred_year_id: int
    pairs: tuple[PairReport, ...]
    institution_kind_unknown: int
    course_projection_conflicts: int


def pair_report(
    scope: PairScope,
    stored: Sequence[NormalizedAgreement],
    excluded: Sequence[Exclusion],
) -> PairReport:
    """One pair's scope plus its normalize outcome.

    A fetch failure recorded by the walk is an excluded agreement here: from
    the report's point of view "we could not fetch it" and "we could not parse
    it" are the same fact, differing only in their typed reason code.
    """
    fetch_failures = [
        Exclusion(failure.assist_key, None, failure.reason_code, failure.detail)
        for failure in scope.fetch_failures
    ]
    articulation_exclusions = [
        exclusion for agreement in stored for exclusion in agreement.exclusions
    ]
    return PairReport(
        sending_id=scope.sending_id,
        receiving_id=scope.receiving_id,
        year_id=scope.year_id,
        major_reports=scope.major_reports,
        major_selected=scope.major_selected,
        dept_reports=scope.dept_reports,
        dept_selected=scope.dept_selected,
        agreements_stored=len(stored),
        agreements_excluded=tuple([*fetch_failures, *excluded]),
        articulations_stored=sum(len(agreement.articulations) for agreement in stored),
        articulations_excluded=tuple(articulation_exclusions),
    )


def build_report(
    scope: CorridorScope,
    pairs: Mapping[tuple[int, int], PairReport],
    *,
    institution_kind_unknown: int,
    course_projection_conflicts: int,
) -> BuildReport:
    """Fold the walk and the per-pair outcomes into the committed report.

    Pair order follows the walk (cc id asc, target id asc), so the file's
    diff between two builds is about what changed at ASSIST, not about
    iteration order.
    """
    return BuildReport(
        targets=scope.targets,
        sending_count=scope.sending_count,
        preferred_year_id=scope.preferred_year_id,
        pairs=tuple(
            pairs[(pair.sending_id, pair.receiving_id)]
            for pair in scope.pairs
            if (pair.sending_id, pair.receiving_id) in pairs
        ),
        institution_kind_unknown=institution_kind_unknown,
        course_projection_conflicts=course_projection_conflicts,
    )


def _exclusion_object(exclusion: Exclusion, *, with_position: bool) -> dict[str, object]:
    entry: dict[str, object] = {"assist_key": exclusion.assist_key}
    if with_position:
        entry["position"] = exclusion.position
    entry["reason_code"] = exclusion.reason_code.value
    entry["detail"] = exclusion.detail
    return entry


def _pair_object(pair: PairReport) -> dict[str, object]:
    return {
        "sending_id": pair.sending_id,
        "receiving_id": pair.receiving_id,
        "year_id": pair.year_id,
        "major_reports": pair.major_reports,
        "major_selected": pair.major_selected,
        "dept_reports": pair.dept_reports,
        "dept_selected": pair.dept_selected,
        "agreements_stored": pair.agreements_stored,
        "agreements_excluded": [
            _exclusion_object(exclusion, with_position=False)
            for exclusion in pair.agreements_excluded
        ],
        "articulations_stored": pair.articulations_stored,
        "articulations_excluded": [
            _exclusion_object(exclusion, with_position=True)
            for exclusion in pair.articulations_excluded
        ],
    }


def _count(exclusions: Iterable[Exclusion], code: AssistBuildCode) -> int:
    return sum(1 for exclusion in exclusions if exclusion.reason_code is code)


def report_object(report: BuildReport) -> dict[str, object]:
    every_exclusion = [
        exclusion
        for pair in report.pairs
        for exclusion in (*pair.agreements_excluded, *pair.articulations_excluded)
    ]
    return {
        "corridor": {
            "targets": list(report.targets),
            "sending_count": report.sending_count,
            "preferred_year_id": report.preferred_year_id,
        },
        "pairs": [_pair_object(pair) for pair in report.pairs],
        "totals": {
            "agreements_stored": sum(pair.agreements_stored for pair in report.pairs),
            "agreements_excluded": sum(len(pair.agreements_excluded) for pair in report.pairs),
            "articulations_excluded": sum(
                len(pair.articulations_excluded) for pair in report.pairs
            ),
            "institution_kind_unknown": report.institution_kind_unknown,
            "course_projection_conflicts": report.course_projection_conflicts,
            "advisement_shape_unknown": _count(
                every_exclusion, AssistBuildCode.ADVISEMENT_SHAPE_UNKNOWN
            ),
        },
    }


def render_report(report: BuildReport) -> str:
    """The exact bytes of the committed file; this recipe IS the determinism."""
    return json.dumps(report_object(report), indent=REPORT_INDENT, sort_keys=True) + "\n"


def write_report(path: Path, report: BuildReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_report(report), encoding="utf-8")
