"""Evaluate a demo student file against the committed artifact (doc 03 CLI).

The Week 1 milestone composition root: load the agreement bundle through the
`assist/store.py` read surface, resolve the student file's courses against the
`cc_courses` projection (exact match only at this increment; fuzzy arrives
with increment 7), build the evaluation, and print the triage board as plain
text with citations.

Everything here is deterministic given the database and the student file; the
only non-injected values are the minted evaluation id and the timestamp,
exactly as `build_evaluation` documents.

`--costs` is not in doc 03's flag list but is required by its exit criteria
(units AND dollar totals verified against the curated cost table): the cost
table location must be explicit, never invented. A missing file at the default
path is reported and evaluated without dollars; an explicitly given path that
does not exist is an error.
"""

import argparse
import json
import sys
from pathlib import Path

from starmap.assist.store import ArticulationStore
from starmap.common.clock import SystemClock
from starmap.common.ids import UuidIdGenerator
from starmap.common.sqlite import SqliteDatabase
from starmap.contracts.evaluation import Evaluation, Finding
from starmap.contracts.reason_codes import TriageBucket
from starmap.transfer.costs import CostTable, load_cost_table
from starmap.transfer.evaluate import (
    AgreementBundle,
    CourseRequest,
    DeptAgreement,
    build_evaluation,
)
from starmap.transfer.triage import CREDIT_BUCKETS, TriageBoard, build_triage_board

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "articulation.db"
DEFAULT_STUDENT_PATH = REPO_ROOT / "data" / "curated" / "demo_students" / "deanza_ucsd_cs.json"
DEFAULT_COSTS_PATH = REPO_ROOT / "data" / "curated" / "costs.json"

STUDENT_FILE_VERSION = "demo-student-v1"

COLUMN_TITLES: dict[TriageBucket, str] = {
    TriageBucket.TRANSFERS_CLEAN: "TRANSFERS CLEAN",
    TriageBucket.AT_RISK: "AT RISK",
    TriageBucket.NO_ARTICULATION: "NO ARTICULATION",
    TriageBucket.STILL_OWED: "REQUIREMENTS STILL OWED",
}


def load_requests(path: Path) -> list[CourseRequest]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("version") != STUDENT_FILE_VERSION:
        raise ValueError(
            f"student file {path} has version {document.get('version')!r}, "
            f"expected {STUDENT_FILE_VERSION!r}"
        )
    return [
        CourseRequest(course_code=entry["course_code"], units=entry["units"])
        for entry in document["courses"]
    ]


def load_bundle(
    store: ArticulationStore, sending: int, receiving: int, major_key: str
) -> AgreementBundle:
    agreements = store.load_agreements_for_pair(sending, receiving)
    majors = [item for item in agreements if item.assist_key == major_key]
    if not majors:
        raise ValueError(
            f"no agreement with key {major_key!r} exists for pair {sending} -> {receiving}"
        )
    major = majors[0]
    latest_year_id = store.latest_year_for_pair(sending, receiving)
    assert latest_year_id is not None  # the pair has at least the major agreement
    labels = {year.year_id: year.label for year in store.load_academic_years()}
    return AgreementBundle(
        major=major,
        major_articulations=tuple(store.load_articulations(major.agreement_id)),
        requirement_groups=tuple(store.load_requirements(major.agreement_id)),
        dept_agreements=tuple(
            DeptAgreement(
                agreement=item,
                articulations=tuple(store.load_articulations(item.agreement_id)),
            )
            for item in agreements
            if item.category == "dept"
        ),
        latest_year_id=latest_year_id,
        latest_year_label=labels[latest_year_id],
    )


def render_finding(finding: Finding) -> list[str]:
    """One finding as indented plain text; every citation is printed."""
    left = ", ".join(finding.student_course_codes) or "(no student course)"
    if finding.receiving_course_code is not None:
        right = finding.receiving_course_code
    elif finding.receiving_course_title is not None:
        right = finding.receiving_course_title
    else:
        right = "(no receiving course)"
    lines = [f"  [{finding.code.value}] {left} -> {right}  ({finding.units:g} units)"]
    if finding.receiving_course_code is not None and finding.receiving_course_title is not None:
        lines.append(f"      receiving title: {finding.receiving_course_title}")
    if finding.detail is not None:
        lines.append(f"      detail: {finding.detail}")
    for advisement in finding.advisements:
        lines.append(f"      advisement: {advisement}")
    if finding.citation is not None:
        lines.append(
            f"      cite: {finding.citation.assist_key} position {finding.citation.position} "
            f"({finding.citation.year_label})"
        )
    return lines


def render_board(evaluation: Evaluation, board: TriageBoard, major_label: str) -> str:
    header = board.header
    lines = [
        "Foothold transfer triage",
        f"Pair: {evaluation.sending_institution_id} -> {evaluation.receiving_institution_id}",
        f"Major: {major_label}",
        f"Major key: {evaluation.major_key}",
        f"Latest published year: {evaluation.year_label} (id {evaluation.year_id})",
        f"Courses evaluated: {header.course_count}; findings: {header.finding_count}",
        "Units: "
        f"clean {header.clean_units:g}, at risk {header.at_risk_units:g}, "
        f"no articulation {header.no_articulation_units:g}, "
        f"still owed {header.still_owed_units:g}",
        "Dollars at target rate: "
        f"at risk {_dollars_text(header.at_risk_dollars)}, "
        f"no articulation {_dollars_text(header.no_articulation_dollars)}",
    ]
    for bucket in CREDIT_BUCKETS:
        findings = board.columns[bucket]
        lines.append("")
        lines.append(f"{COLUMN_TITLES[bucket]} ({len(findings)})")
        for finding in findings:
            lines.extend(render_finding(finding))
    lines.append("")
    lines.append(f"{COLUMN_TITLES[TriageBucket.STILL_OWED]} ({len(board.still_owed)})")
    for finding in board.still_owed:
        lines.extend(render_finding(finding))
    lines.append("")
    lines.append("Data: ASSIST.org, the official California articulation repository")
    return "\n".join(lines)


def _dollars_text(value: float | None) -> str:
    return "unknown (no cost row)" if value is None else f"${value:,.2f}"


def run(
    db_path: Path,
    student_path: Path,
    costs_path: Path | None,
    sending: int,
    receiving: int,
    major_key: str,
) -> int:
    cost_table: CostTable | None = None
    if costs_path is not None:
        cost_table = load_cost_table(costs_path)
    store = ArticulationStore(SqliteDatabase(db_path))
    bundle = load_bundle(store, sending, receiving, major_key)
    vocabulary = frozenset(course.course_code for course in store.load_cc_courses(sending))
    evaluation = build_evaluation(
        requests=load_requests(student_path),
        vocabulary=vocabulary,
        bundle=bundle,
        id_generator=UuidIdGenerator(),
        clock=SystemClock(),
        cost_table=cost_table,
    )
    board = build_triage_board(evaluation)
    print(render_board(evaluation, board, bundle.major.label))
    if cost_table is None:
        print("note: no cost table loaded; dollar fields are None by construction")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate a student file against the articulation artifact."
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="artifact path")
    parser.add_argument(
        "--student", type=Path, default=DEFAULT_STUDENT_PATH, help="demo student JSON file"
    )
    parser.add_argument(
        "--costs",
        type=Path,
        default=None,
        help=f"curated cost table (default {DEFAULT_COSTS_PATH} when it exists)",
    )
    parser.add_argument("--sending", type=int, default=113, help="sending institution id")
    parser.add_argument("--receiving", type=int, default=7, help="receiving institution id")
    parser.add_argument("--major-key", required=True, help="assist key of the major agreement")
    arguments = parser.parse_args(argv)

    costs_path: Path | None = arguments.costs
    if costs_path is None and DEFAULT_COSTS_PATH.exists():
        costs_path = DEFAULT_COSTS_PATH
    if arguments.costs is not None and not arguments.costs.exists():
        parser.error(f"cost table {arguments.costs} does not exist")
    if not arguments.db.exists():
        parser.error(f"database {arguments.db} does not exist (run `make unpack-data`)")
    if not arguments.student.exists():
        parser.error(f"student file {arguments.student} does not exist")

    return run(
        db_path=arguments.db,
        student_path=arguments.student,
        costs_path=costs_path,
        sending=arguments.sending,
        receiving=arguments.receiving,
        major_key=arguments.major_key,
    )


if __name__ == "__main__":
    sys.exit(main())
