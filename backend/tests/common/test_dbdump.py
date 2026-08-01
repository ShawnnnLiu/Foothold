import sqlite3
from collections.abc import Iterable
from pathlib import Path

import pytest

from starmap.common.dbdump import canonical_dump
from starmap.common.sqlite import SqliteDatabase, ensure_schema

STATEMENTS = [
    "CREATE TABLE IF NOT EXISTS courses (course_code TEXT PRIMARY KEY, title TEXT NOT NULL)"
]

ROWS = [
    ("COMS W1004", "Intro to CS"),
    ("COMS W3134", "Data Structures"),
    ("COMS W4701", "Artificial Intelligence"),
]


def build_db(path: Path, rows: Iterable[tuple[str, str]]) -> None:
    db = SqliteDatabase(path)
    ensure_schema(db, "catalog", version=1, statements=STATEMENTS)
    with db.transaction() as cursor:
        cursor.executemany("INSERT INTO courses VALUES (?, ?)", rows)
    db.close()


def test_dump_is_invariant_to_insert_order(tmp_path: Path) -> None:
    build_db(tmp_path / "a.db", ROWS)
    build_db(tmp_path / "b.db", reversed(ROWS))
    assert canonical_dump(tmp_path / "a.db") == canonical_dump(tmp_path / "b.db")


def test_dump_differs_after_row_mutation(tmp_path: Path) -> None:
    build_db(tmp_path / "a.db", ROWS)
    build_db(tmp_path / "b.db", ROWS)
    db = SqliteDatabase(tmp_path / "b.db")
    with db.transaction() as cursor:
        cursor.execute("UPDATE courses SET title = 'Mutated' WHERE course_code = 'COMS W1004'")
    db.close()
    assert canonical_dump(tmp_path / "a.db") != canonical_dump(tmp_path / "b.db")


def test_schema_version_table_is_included(tmp_path: Path) -> None:
    build_db(tmp_path / "a.db", ROWS)
    dump = canonical_dump(tmp_path / "a.db")
    assert "schema_version" in dump
    assert '["catalog", 1]' in dump


def test_fts_shadow_rows_excluded_but_virtual_create_included(tmp_path: Path) -> None:
    path = tmp_path / "a.db"
    connection = sqlite3.connect(path)
    try:
        connection.execute("CREATE VIRTUAL TABLE notes_fts USING fts5(body)")
    except sqlite3.OperationalError:  # pragma: no cover - platform without FTS5
        connection.close()
        pytest.skip("FTS5 unavailable in this SQLite build")
    connection.execute("INSERT INTO notes_fts VALUES ('hello searchable world')")
    connection.commit()
    connection.close()

    dump = canonical_dump(path)
    assert "CREATE VIRTUAL TABLE notes_fts USING fts5(body)" in dump
    assert "hello searchable world" not in dump
