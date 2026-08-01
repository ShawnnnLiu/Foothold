"""SQLite kernel shared by every region (stdlib-only).

Connection discipline (tech reference 4.3):

- the connection is autocommit (`isolation_level=None`), so transaction
  boundaries are ONLY the explicit BEGIN IMMEDIATE / COMMIT / ROLLBACK
  issued by `transaction()`;
- WAL journal mode and foreign keys are enabled at open;
- one `threading.RLock` serializes every transaction and read, which is
  what makes `check_same_thread=False` safe: two threads can never observe
  a torn write;
- transactions NEVER nest: a store method does all its SQL inside one
  `transaction()` block and never calls another method that opens its own
  transaction while one is active. Practical consequence: read everything
  you need from other stores BEFORE opening your write transaction.
"""

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from starmap.common.errors import StarmapError


class SchemaVersionMismatchError(StarmapError):
    """The on-disk schema version differs from what the component expects.

    Raised INSTEAD of migrating: there is no migration framework; fail
    loudly rather than guess.
    """

    def __init__(self, component: str, on_disk: int, expected: int) -> None:
        super().__init__(
            f"schema version mismatch for component {component!r}: "
            f"on-disk version is {on_disk}, expected {expected}"
        )
        self.component = component
        self.on_disk = on_disk
        self.expected = expected


class SqliteDatabase:
    """A serialized SQLite connection with explicit transaction boundaries."""

    def __init__(self, path: Path | str) -> None:
        self._conn = sqlite3.connect(
            str(path),
            check_same_thread=False,
            isolation_level=None,
        )
        self._lock = threading.RLock()
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Cursor]:
        """One write transaction: commit on clean exit, rollback on ANY exception."""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                cursor.execute("BEGIN IMMEDIATE")
                yield cursor
                self._conn.execute("COMMIT")
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            finally:
                cursor.close()

    @contextmanager
    def read(self) -> Iterator[sqlite3.Cursor]:
        """A serialized read-only cursor in autocommit (no write lock taken)."""
        with self._lock:
            cursor = self._conn.cursor()
            try:
                yield cursor
            finally:
                cursor.close()

    def close(self) -> None:
        self._conn.close()


def ensure_schema(
    db: SqliteDatabase,
    component: str,
    *,
    version: int,
    statements: Sequence[str],
) -> None:
    """Create a component's schema and record its version, inside one transaction.

    If the component already has a recorded version and it differs, raise
    `SchemaVersionMismatchError`. Statements must each be idempotent
    (`CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`), so a
    re-run at the same version is a no-op.
    """
    with db.transaction() as cursor:
        cursor.execute(
            "CREATE TABLE IF NOT EXISTS schema_version ("
            "component TEXT PRIMARY KEY, version INTEGER NOT NULL)"
        )
        cursor.execute(
            "SELECT version FROM schema_version WHERE component = ?",
            (component,),
        )
        row = cursor.fetchone()
        if row is not None and row[0] != version:
            raise SchemaVersionMismatchError(component, on_disk=row[0], expected=version)
        for statement in statements:
            cursor.execute(statement)
        if row is None:
            cursor.execute(
                "INSERT INTO schema_version (component, version) VALUES (?, ?)",
                (component, version),
            )
