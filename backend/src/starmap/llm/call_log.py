"""Append-only call-log store (tech reference 4.2).

Canonical spec: docs/specs/llm_call_log.schema.md.
Cost tracking is how the contest budget stays honest, so every provider call
appends exactly one row, including calls that failed in transport.
"""

from typing import Protocol, runtime_checkable

from starmap.common.errors import StarmapError
from starmap.common.sqlite import SqliteDatabase, ensure_schema
from starmap.contracts.llm_call_log import LlmCallLogRecord

COMPONENT = "llm_call_log"
SCHEMA_VERSION = 1
STATEMENTS = (
    "CREATE TABLE IF NOT EXISTS llm_call_logs ("
    "llm_call_log_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS idx_llm_call_logs_run_id ON llm_call_logs (run_id)",
)


class CallLogAlreadyExistsError(StarmapError):
    """A row with this `llm_call_log_id` is already stored."""

    def __init__(self, llm_call_log_id: str) -> None:
        super().__init__(f"call log row {llm_call_log_id!r} already exists")
        self.llm_call_log_id = llm_call_log_id


@runtime_checkable
class CallLogStore(Protocol):
    """The narrow seam the engine writes through."""

    def append(self, record: LlmCallLogRecord) -> None: ...


class SqliteCallLogStore:
    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db
        ensure_schema(db, COMPONENT, version=SCHEMA_VERSION, statements=STATEMENTS)

    def append(self, record: LlmCallLogRecord) -> None:
        """Insert one row; a duplicate id is a typed error, never a caught PK violation."""
        payload = record.model_dump_json()
        with self._db.transaction() as cursor:
            cursor.execute(
                "SELECT 1 FROM llm_call_logs WHERE llm_call_log_id = ?",
                (record.llm_call_log_id,),
            )
            if cursor.fetchone() is not None:
                raise CallLogAlreadyExistsError(record.llm_call_log_id)
            cursor.execute(
                "INSERT INTO llm_call_logs (llm_call_log_id, run_id, payload) VALUES (?, ?, ?)",
                (record.llm_call_log_id, record.run_id, payload),
            )

    def list_for_run(self, run_id: str) -> list[LlmCallLogRecord]:
        """Rows for one run, in insertion order; reads re-validate."""
        with self._db.read() as cursor:
            cursor.execute(
                "SELECT payload FROM llm_call_logs WHERE run_id = ? ORDER BY rowid",
                (run_id,),
            )
            rows = cursor.fetchall()
        return [LlmCallLogRecord.model_validate_json(row[0]) for row in rows]

    def list_all(self) -> list[LlmCallLogRecord]:
        """Every row, in insertion order; reads re-validate."""
        with self._db.read() as cursor:
            cursor.execute("SELECT payload FROM llm_call_logs ORDER BY rowid")
            rows = cursor.fetchall()
        return [LlmCallLogRecord.model_validate_json(row[0]) for row in rows]
