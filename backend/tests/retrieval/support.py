"""Shared builders for the retrieval tests: real temp SQLite, never faked."""

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from starmap.common.sqlite import SqliteDatabase
from starmap.contracts.cc_course import CcCourse
from starmap.retrieval.index import CourseIndex, SearchHit

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "retrieval"


def make_course(
    institution_id: int, prefix: str, number: str, title: str, units: float
) -> CcCourse:
    return CcCourse(
        institution_id=institution_id,
        course_code=f"{prefix} {number}",
        prefix=prefix,
        number=number,
        title=title,
        units_min=units,
        units_max=units,
    )


def load_resolve_fixture() -> dict[str, Any]:
    document = json.loads((FIXTURES_ROOT / "resolve_cases.json").read_text(encoding="utf-8"))
    assert isinstance(document, dict)
    return document


def fixture_courses(document: dict[str, Any], institution_id: int) -> list[CcCourse]:
    return [
        make_course(row["institution_id"], row["prefix"], row["number"], row["title"], row["units"])
        for row in document["courses"]
        if row["institution_id"] == institution_id
    ]


def build_fixture_index(db_path: Path) -> CourseIndex:
    """The fixture vocabulary, indexed per institution into one temp corpus."""
    document = load_resolve_fixture()
    index = CourseIndex(SqliteDatabase(db_path))
    institution_ids = sorted({row["institution_id"] for row in document["courses"]})
    for institution_id in institution_ids:
        index.build(institution_id, fixture_courses(document, institution_id))
    return index


def serialized(hits: list[SearchHit]) -> bytes:
    """Byte-stable serialization for the determinism and isolation pins."""
    return json.dumps([asdict(hit) for hit in hits], sort_keys=True).encode()
