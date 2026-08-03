"""`sessions.db`: session-keyed persistence for evaluations and LLM jobs.

The only mutable database (`CLAUDE.md`); `SqliteCallLogStore` shares the same
file, each component owning its own schema triple. Every `get` filters by the
middleware-derived sid and revalidates the payload through the contract
(rebuild-through-validation, TR 4.5), so a row that drifted from its model
fails at read time instead of flowing to a client, and an unknown id and
another session's id are indistinguishable (the uniform 404).
"""

from collections.abc import Iterable
from datetime import datetime

from starmap.common.sqlite import SqliteDatabase, ensure_schema
from starmap.contracts.evaluation import Evaluation
from starmap.contracts.petition import Petition
from starmap.contracts.transcript_parse import TranscriptParse

# Decision 6 (docs/implementation-plans/llm-nodes/00-overview.md): four times
# the client's 30-second poll cap, so a live job is never falsely abandoned.
PENDING_TTL_SECONDS = 120

COMPONENT = "evaluations"
SCHEMA_VERSION = 1

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS evaluations (
        evaluation_id TEXT PRIMARY KEY, sid TEXT NOT NULL,
        created_at TEXT NOT NULL, payload TEXT NOT NULL)
    """,
    "CREATE INDEX IF NOT EXISTS evaluations_by_sid ON evaluations (sid)",
)

PARSES_COMPONENT = "transcript_parses"
PARSES_SCHEMA_VERSION = 1

PARSES_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS transcript_parses (
        parse_id TEXT PRIMARY KEY, sid TEXT NOT NULL,
        created_at TEXT NOT NULL, payload TEXT NOT NULL)
    """,
    "CREATE INDEX IF NOT EXISTS transcript_parses_by_sid ON transcript_parses (sid)",
)

PETITIONS_COMPONENT = "petitions"
PETITIONS_SCHEMA_VERSION = 1

PETITIONS_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS petitions (
        petition_id TEXT PRIMARY KEY, sid TEXT NOT NULL,
        evaluation_id TEXT NOT NULL, selection_key TEXT NOT NULL,
        created_at TEXT NOT NULL, payload TEXT NOT NULL)
    """,
    "CREATE INDEX IF NOT EXISTS petitions_by_sid ON petitions (sid)",
    "CREATE INDEX IF NOT EXISTS petitions_by_selection "
    "ON petitions (sid, evaluation_id, selection_key)",
)


def selection_key(finding_positions: Iterable[int]) -> str:
    """The pending-duplicate key: one canonical spelling per selection."""
    return ",".join(str(position) for position in sorted(finding_positions))


class EvaluationStore:
    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db
        ensure_schema(db, COMPONENT, version=SCHEMA_VERSION, statements=SCHEMA_STATEMENTS)

    def put(self, sid: str, evaluation: Evaluation) -> None:
        with self._db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO evaluations (evaluation_id, sid, created_at, payload) "
                "VALUES (?, ?, ?, ?)",
                (
                    evaluation.evaluation_id,
                    sid,
                    evaluation.created_at.isoformat(),
                    evaluation.model_dump_json(),
                ),
            )

    def get(self, sid: str, evaluation_id: str) -> Evaluation | None:
        """The stored evaluation, or None when the id is unknown OR owned by
        another session; the route maps both to one uniform 404."""
        with self._db.read() as cursor:
            cursor.execute(
                "SELECT payload FROM evaluations WHERE evaluation_id = ? AND sid = ?",
                (evaluation_id, sid),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return Evaluation.model_validate_json(row[0])


class TranscriptParseStore:
    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db
        ensure_schema(
            db,
            PARSES_COMPONENT,
            version=PARSES_SCHEMA_VERSION,
            statements=PARSES_SCHEMA_STATEMENTS,
        )

    def put(self, sid: str, parse: TranscriptParse) -> None:
        with self._db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO transcript_parses (parse_id, sid, created_at, payload) "
                "VALUES (?, ?, ?, ?)",
                (
                    parse.parse_id,
                    sid,
                    parse.created_at.isoformat(),
                    parse.model_dump_json(),
                ),
            )

    def finish(self, parse: TranscriptParse) -> None:
        """The background task's only write; the row's sid never changes."""
        with self._db.transaction() as cursor:
            cursor.execute(
                "UPDATE transcript_parses SET payload = ? WHERE parse_id = ?",
                (parse.model_dump_json(), parse.parse_id),
            )

    def get(self, sid: str, parse_id: str) -> TranscriptParse | None:
        with self._db.read() as cursor:
            cursor.execute(
                "SELECT payload FROM transcript_parses WHERE parse_id = ? AND sid = ?",
                (parse_id, sid),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return TranscriptParse.model_validate_json(row[0])


class PetitionStore:
    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db
        ensure_schema(
            db,
            PETITIONS_COMPONENT,
            version=PETITIONS_SCHEMA_VERSION,
            statements=PETITIONS_SCHEMA_STATEMENTS,
        )

    def put(self, sid: str, petition: Petition) -> None:
        with self._db.transaction() as cursor:
            cursor.execute(
                "INSERT INTO petitions "
                "(petition_id, sid, evaluation_id, selection_key, created_at, payload) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    petition.petition_id,
                    sid,
                    petition.evaluation_id,
                    selection_key(petition.finding_positions),
                    petition.created_at.isoformat(),
                    petition.model_dump_json(),
                ),
            )

    def finish(self, petition: Petition) -> None:
        """The background task's only write; the row's sid never changes."""
        with self._db.transaction() as cursor:
            cursor.execute(
                "UPDATE petitions SET payload = ? WHERE petition_id = ?",
                (petition.model_dump_json(), petition.petition_id),
            )

    def get(self, sid: str, petition_id: str) -> Petition | None:
        with self._db.read() as cursor:
            cursor.execute(
                "SELECT payload FROM petitions WHERE petition_id = ? AND sid = ?",
                (petition_id, sid),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return Petition.model_validate_json(row[0])

    def pending_exists(self, sid: str, evaluation_id: str, key: str, *, now: datetime) -> bool:
        """True when this selection already has a live pending job (decision 6).

        A pending row younger than `PENDING_TTL_SECONDS` blocks a duplicate;
        an older one is treated as abandoned. Payload parsing stays inside one
        `read()` block: the matching key holds at most a handful of rows.
        """
        with self._db.read() as cursor:
            cursor.execute(
                "SELECT payload FROM petitions "
                "WHERE sid = ? AND evaluation_id = ? AND selection_key = ?",
                (sid, evaluation_id, key),
            )
            for (payload,) in cursor.fetchall():
                petition = Petition.model_validate_json(payload)
                if petition.status != "pending":
                    continue
                if (now - petition.created_at).total_seconds() < PENDING_TTL_SECONDS:
                    return True
        return False
