"""`sessions.db`: evaluation persistence keyed by session (doc 01).

The only mutable database (`CLAUDE.md`); `SqliteCallLogStore` will share this
file in the LLM-node increments, each component owning its own schema triple.
`get` filters by the middleware-derived sid and revalidates the payload
through the contract (rebuild-through-validation, TR 4.5), so a row that
drifted from its model fails at read time instead of flowing to a client.
"""

from starmap.common.sqlite import SqliteDatabase, ensure_schema
from starmap.contracts.evaluation import Evaluation

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
