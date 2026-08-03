"""`articulation.db`: determinism and payload round trips.

SQLite is never faked (testing strategy, "Hard Rules"), so every test here
writes a real database under `tmp_path` with the real schema.

The determinism test is the CI half of the committed-artifact gate: the raw
ASSIST cache is gitignored and far too large for CI to regenerate the corridor,
so `make build-check` proves identity locally over the real artifact while this
proves the same property over the fixtures on every push.
"""

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from starmap.assist.normalize import (
    AcademicYear,
    NormalizedAgreement,
    dedupe_course_rows,
    normalize_academic_years,
    normalize_agreement,
    normalize_institutions,
)
from starmap.assist.store import ArticulationStore
from starmap.common.dbdump import canonical_dump
from starmap.common.sqlite import SqliteDatabase

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "assist"
MAJOR_KEY = "76/113/to/7/Major/f8d5b3e6-1d24-4b7a-9a3f-1b2c3d4e5f60"
DEPT_KEY = "76/113/to/7/Department/12"
DE_ANZA = 113
UCSD = 7


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def normalized_agreements() -> list[NormalizedAgreement]:
    """The demo pair's two captured agreements, in sorted `assist_key` order."""
    agreements = [
        normalize_agreement(
            fixture("agreement_major_cse_cs_113_to_7_y76.json"),
            assist_key=MAJOR_KEY,
            category="major",
            label="Mathematics/Computer Science B.S.",
            sending_id=DE_ANZA,
            receiving_id=UCSD,
        ),
        normalize_agreement(
            fixture("agreement_dept_math_113_to_7_y76.json"),
            assist_key=DEPT_KEY,
            category="dept",
            label="Mathematics",
            sending_id=DE_ANZA,
            receiving_id=UCSD,
        ),
    ]
    return sorted(agreements, key=lambda item: item.agreement.assist_key)


def build(path: Path, *, agreements: list[NormalizedAgreement] | None = None) -> None:
    """Write a complete artifact the way the build script does."""
    items = normalized_agreements() if agreements is None else agreements
    institutions, _ = normalize_institutions(fixture("institutions.json"))
    years = normalize_academic_years(fixture("academic_years.json"))
    cc_courses, _ = dedupe_course_rows([course for item in items for course in item.cc_courses])
    targets, _ = dedupe_course_rows([course for item in items for course in item.target_courses])

    db = SqliteDatabase(path)
    try:
        store = ArticulationStore(db)
        store.put_institutions(institutions)
        store.put_academic_years(years)
        store.put_agreements(items)
        store.put_cc_courses(cc_courses)
        store.put_target_courses(targets)
        store.vacuum()
    finally:
        db.close()


@pytest.fixture
def artifact(tmp_path: Path) -> Path:
    path = tmp_path / "articulation.db"
    build(path)
    return path


def opened(path: Path) -> tuple[SqliteDatabase, ArticulationStore]:
    db = SqliteDatabase(path)
    return db, ArticulationStore(db)


# --- determinism ------------------------------------------------------------


def test_two_builds_of_the_same_fixtures_are_identical(tmp_path: Path) -> None:
    first = tmp_path / "first.db"
    second = tmp_path / "second.db"
    build(first)
    build(second)
    assert canonical_dump(first) == canonical_dump(second)


def test_reversing_the_insert_order_does_not_change_the_artifact(tmp_path: Path) -> None:
    """The store sorts rather than trusting its caller, so the artifact cannot
    record the order agreements happened to be normalized in."""
    forward = tmp_path / "forward.db"
    reverse = tmp_path / "reverse.db"
    build(forward)
    build(reverse, agreements=list(reversed(normalized_agreements())))
    assert canonical_dump(forward) == canonical_dump(reverse)


def test_the_dump_carries_the_schema_version_and_no_timestamps(artifact: Path) -> None:
    dump = canonical_dump(artifact)
    assert '["articulation", 1]' in dump
    assert "fetched_at" not in dump


def test_a_mutated_row_changes_the_dump(artifact: Path) -> None:
    before = canonical_dump(artifact)
    connection = sqlite3.connect(artifact)
    try:
        connection.execute("UPDATE academic_years SET label = 'tampered' WHERE year_id = 76")
        connection.commit()
    finally:
        connection.close()
    assert canonical_dump(artifact) != before


# --- payload round trips ----------------------------------------------------


def test_agreements_round_trip_through_their_contract(artifact: Path) -> None:
    db, store = opened(artifact)
    try:
        agreements = store.load_agreements_for_pair(DE_ANZA, UCSD)
        assert [item.assist_key for item in agreements] == sorted([DEPT_KEY, MAJOR_KEY])
        assert {item.category for item in agreements} == {"major", "dept"}
    finally:
        db.close()


def test_articulations_round_trip_in_position_order(artifact: Path) -> None:
    db, store = opened(artifact)
    try:
        (major,) = [
            item
            for item in store.load_agreements_for_pair(DE_ANZA, UCSD)
            if item.category == "major"
        ]
        articulations = store.load_articulations(major.agreement_id)
        assert [item.position for item in articulations] == list(range(8))
        receiving = articulations[3].receiving_course
        assert receiving is not None
        assert receiving.course_code == "MATH 20E"
        assert articulations[3].sending_expr is not None
    finally:
        db.close()


def test_requirement_groups_round_trip_with_their_cells(artifact: Path) -> None:
    db, store = opened(artifact)
    try:
        (major,) = [
            item
            for item in store.load_agreements_for_pair(DE_ANZA, UCSD)
            if item.category == "major"
        ]
        groups = store.load_requirements(major.agreement_id)
        assert [group.position for group in groups] == [0, 1, 2, 3]
        assert groups[3].conjunction == "Or"
        cells = [cell for section in groups[3].sections for cell in section.cells]
        assert [cell.course.course_code for cell in cells if cell.course is not None] == [
            "CSE 15L",
            "CSE 29",
        ]
    finally:
        db.close()


def test_a_dept_agreement_stores_no_requirement_groups(artifact: Path) -> None:
    db, store = opened(artifact)
    try:
        (department,) = [
            item
            for item in store.load_agreements_for_pair(DE_ANZA, UCSD)
            if item.category == "dept"
        ]
        assert store.load_requirements(department.agreement_id) == []
        assert len(store.load_articulations(department.agreement_id)) == 11
    finally:
        db.close()


def test_both_projections_round_trip_per_institution(artifact: Path) -> None:
    db, store = opened(artifact)
    try:
        cc_courses = store.load_cc_courses(DE_ANZA)
        targets = store.load_target_courses(UCSD)
        assert [course.course_code for course in cc_courses] == sorted(
            course.course_code for course in cc_courses
        )
        assert "CIS 22CH" in {course.course_code for course in cc_courses}
        assert {"CSE 15L", "CSE 29"} <= {course.course_code for course in targets}
        assert store.load_cc_courses(UCSD) == []
    finally:
        db.close()


def test_institutions_and_years_round_trip(artifact: Path) -> None:
    db, store = opened(artifact)
    try:
        institutions = store.load_institutions()
        assert len(institutions) == 148
        assert {item.assist_id: item.kind for item in institutions}[DE_ANZA] == "cc"
        assert AcademicYear(year_id=76, label="2025-2026", fall_year=2025) in (
            store.load_academic_years()
        )
    finally:
        db.close()


def test_the_latest_year_for_a_pair_is_derived_from_its_agreements(artifact: Path) -> None:
    """No table records it, so it can never disagree with the agreements."""
    db, store = opened(artifact)
    try:
        assert store.latest_year_for_pair(DE_ANZA, UCSD) == 76
        assert store.latest_year_for_pair(DE_ANZA, 999) is None
    finally:
        db.close()


def test_reopening_an_existing_artifact_is_a_no_op(artifact: Path) -> None:
    """`ensure_schema` at the same version must not rewrite anything."""
    before = canonical_dump(artifact)
    db, _ = opened(artifact)
    db.close()
    assert canonical_dump(artifact) == before
