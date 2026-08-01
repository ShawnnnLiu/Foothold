import sqlite3
import threading
from pathlib import Path

import pytest

from starmap.common.errors import StarmapError
from starmap.common.sqlite import SchemaVersionMismatchError, SqliteDatabase, ensure_schema


def test_wal_and_foreign_keys_enabled(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "t.db")
    with db.read() as cursor:
        cursor.execute("PRAGMA journal_mode")
        assert cursor.fetchone()[0] == "wal"
        cursor.execute("PRAGMA foreign_keys")
        assert cursor.fetchone()[0] == 1
    db.close()


def test_commit_persists_across_reopen(tmp_path: Path) -> None:
    path = tmp_path / "t.db"
    db = SqliteDatabase(path)
    with db.transaction() as cursor:
        cursor.execute("CREATE TABLE t (x INTEGER)")
        cursor.execute("INSERT INTO t VALUES (1)")
    db.close()

    reopened = SqliteDatabase(path)
    with reopened.read() as cursor:
        cursor.execute("SELECT x FROM t")
        assert cursor.fetchall() == [(1,)]
    reopened.close()


def test_rollback_on_any_exception(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "t.db")
    with db.transaction() as cursor:
        cursor.execute("CREATE TABLE t (x INTEGER)")
        cursor.execute("INSERT INTO t VALUES (1)")

    with pytest.raises(RuntimeError, match="boom"), db.transaction() as cursor:
        cursor.execute("INSERT INTO t VALUES (2)")
        raise RuntimeError("boom")

    with db.read() as cursor:
        cursor.execute("SELECT x FROM t")
        assert cursor.fetchall() == [(1,)]
    db.close()


def test_foreign_keys_enforced(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "t.db")
    with db.transaction() as cursor:
        cursor.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        cursor.execute("CREATE TABLE child (pid INTEGER REFERENCES parent(id))")
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as cursor:
        cursor.execute("INSERT INTO child VALUES (99)")
    db.close()


def test_concurrent_transactions_are_serialized(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "t.db")
    with db.transaction() as cursor:
        cursor.execute("CREATE TABLE counter (value INTEGER)")
        cursor.execute("INSERT INTO counter VALUES (0)")

    errors: list[BaseException] = []

    def worker() -> None:
        try:
            for _ in range(50):
                with db.transaction() as cursor:
                    cursor.execute("SELECT value FROM counter")
                    current = cursor.fetchone()[0]
                    cursor.execute("UPDATE counter SET value = ?", (current + 1,))
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    with db.read() as cursor:
        cursor.execute("SELECT value FROM counter")
        assert cursor.fetchone()[0] == 100
    db.close()


STATEMENTS = ["CREATE TABLE IF NOT EXISTS things (id TEXT PRIMARY KEY)"]


def test_ensure_schema_creates_tables_and_records_version(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "t.db")
    ensure_schema(db, "catalog", version=1, statements=STATEMENTS)
    with db.read() as cursor:
        cursor.execute("SELECT version FROM schema_version WHERE component = 'catalog'")
        assert cursor.fetchone() == (1,)
        cursor.execute("INSERT INTO things VALUES ('a')")
    db.close()


def test_ensure_schema_idempotent_at_same_version(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "t.db")
    ensure_schema(db, "catalog", version=1, statements=STATEMENTS)
    ensure_schema(db, "catalog", version=1, statements=STATEMENTS)
    with db.read() as cursor:
        cursor.execute("SELECT COUNT(*) FROM schema_version WHERE component = 'catalog'")
        assert cursor.fetchone() == (1,)
    db.close()


def test_ensure_schema_version_mismatch_raises_typed_error(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "t.db")
    ensure_schema(db, "catalog", version=1, statements=STATEMENTS)
    with pytest.raises(SchemaVersionMismatchError) as excinfo:
        ensure_schema(
            db,
            "catalog",
            version=2,
            statements=["CREATE TABLE IF NOT EXISTS extra (id TEXT)"],
        )
    error = excinfo.value
    assert isinstance(error, StarmapError)
    assert error.component == "catalog"
    assert error.on_disk == 1
    assert error.expected == 2
    with db.read() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE name = 'extra'")
        assert cursor.fetchone() is None
    db.close()
