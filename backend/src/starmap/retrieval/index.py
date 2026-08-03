"""Per-institution FTS5/BM25 index over the `cc_courses` projection.

Why one FTS table PER INSTITUTION (the TR 1.4 per-snapshot argument,
transplanted): BM25 term statistics are corpus-wide, so a shared table would
let one college's catalog shift another's scores; with per-institution tables
a result is a pure function of (query, institution).

Table-name safety: the institution id is interpolated into the table name only
after `_validated_institution_id` proves it is a positive `int`; the integer
check is what makes the f-string-into-SQL safe, mirroring TR 1.4's regex rule.

The vocabulary gate, wired here: `cc_course_rows` IS the projection served to
UI autocomplete AND consumed by the transcript resolver; one table, two
consumers, never a second extraction from `articulation.db` at request time.
"""

import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass

from starmap.common.sqlite import SqliteDatabase, ensure_schema
from starmap.contracts.cc_course import CcCourse
from starmap.retrieval.errors import Fts5UnavailableError, InstitutionNotIndexedError

COMPONENT = "corpus"
SCHEMA_VERSION = 1

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS cc_course_rows (
        institution_id INTEGER NOT NULL, course_code TEXT NOT NULL, prefix TEXT NOT NULL,
        number TEXT NOT NULL, title TEXT NOT NULL, units_min REAL NOT NULL, units_max REAL NOT NULL,
        PRIMARY KEY (institution_id, course_code))
    """,
    """
    CREATE TABLE IF NOT EXISTS index_builds (
        institution_id INTEGER PRIMARY KEY, course_count INTEGER NOT NULL)
    """,
)

# Module-level so the probe-failure unit test can monkeypatch the statement to
# a bad one even on SQLite builds that do have FTS5.
FTS5_PROBE_STATEMENT = "CREATE VIRTUAL TABLE fts5_probe USING fts5(text)"

_WORD_RE = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class SearchHit:
    course_code: str
    title: str
    units_min: float
    units_max: float
    score: float
    rank: int


def compile_match_expression(query: str) -> str:
    """The TR 1.4 bag-of-words rule: `\\w+` tokens, each double-quoted, OR-joined.

    Quoting makes FTS5 operators (`NEAR`, `AND`, `OR`, `*`, parentheses)
    literals, never syntax. No word tokens compiles to the empty string and the
    caller returns an honest empty result rather than raising.
    """
    tokens = _WORD_RE.findall(query.lower())
    return " OR ".join(f'"{token}"' for token in tokens)


def _validated_institution_id(institution_id: int) -> int:
    if not isinstance(institution_id, int) or institution_id <= 0:
        raise ValueError(f"institution id must be a positive int, got {institution_id!r}")
    return institution_id


def _fts_table(institution_id: int) -> str:
    return f"cc_courses_fts_{_validated_institution_id(institution_id)}"


def _probe_fts5() -> None:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute(FTS5_PROBE_STATEMENT)
    except sqlite3.OperationalError as error:
        raise Fts5UnavailableError() from error
    finally:
        connection.close()


class CourseIndex:
    """Builds and searches `corpus.db`. Writes happen once, at build time."""

    def __init__(self, db: SqliteDatabase) -> None:
        _probe_fts5()
        self._db = db
        ensure_schema(db, COMPONENT, version=SCHEMA_VERSION, statements=SCHEMA_STATEMENTS)

    def build(self, institution_id: int, courses: Sequence[CcCourse]) -> int:
        """Index one institution's projection rows; idempotent.

        An existing `index_builds` row returns the stored count unchanged:
        rows regenerate only through a fresh database build, never in place.
        """
        table = _fts_table(institution_id)
        rows = sorted(courses, key=lambda course: course.course_code)
        with self._db.transaction() as cursor:
            cursor.execute(
                "SELECT course_count FROM index_builds WHERE institution_id = ?",
                (institution_id,),
            )
            existing = cursor.fetchone()
            if existing is not None:
                return int(existing[0])
            cursor.execute(f"CREATE VIRTUAL TABLE IF NOT EXISTS {table} USING fts5(code, title)")
            for course in rows:
                cursor.execute(
                    "INSERT INTO cc_course_rows (institution_id, course_code, prefix, number, "
                    "title, units_min, units_max) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        course.institution_id,
                        course.course_code,
                        course.prefix,
                        course.number,
                        course.title,
                        course.units_min,
                        course.units_max,
                    ),
                )
                cursor.execute(
                    f"INSERT INTO {table} (rowid, code, title) VALUES (?, ?, ?)",
                    (cursor.lastrowid, course.course_code, course.title),
                )
            cursor.execute(
                "INSERT INTO index_builds (institution_id, course_count) VALUES (?, ?)",
                (institution_id, len(rows)),
            )
        return len(rows)

    def search(self, institution_id: int, query: str, k: int = 5) -> list[SearchHit]:
        table = _fts_table(institution_id)
        expression = compile_match_expression(query)
        with self._db.read() as cursor:
            cursor.execute(
                "SELECT course_count FROM index_builds WHERE institution_id = ?",
                (institution_id,),
            )
            if cursor.fetchone() is None:
                raise InstitutionNotIndexedError(institution_id)
            if not expression:
                return []
            cursor.execute(
                f"SELECT c.course_code, c.title, c.units_min, c.units_max, "
                f"-bm25({table}) AS score "
                f"FROM {table} f JOIN cc_course_rows c ON c.rowid = f.rowid "
                f"WHERE c.institution_id = ? AND {table} MATCH ? "
                f"ORDER BY score DESC, c.course_code ASC LIMIT ?",
                (institution_id, expression, k),
            )
            rows = cursor.fetchall()
        return [
            SearchHit(
                course_code=course_code,
                title=title,
                units_min=units_min,
                units_max=units_max,
                score=score,
                rank=rank,
            )
            for rank, (course_code, title, units_min, units_max, score) in enumerate(rows, start=1)
        ]

    def lookup(self, institution_id: int, course_code: str) -> SearchHit | None:
        """One projection row by its exact stored code; the resolver's exact gate.

        The hit carries no BM25 evidence, so `score` is 0.0 and `rank` is 1 by
        convention: an exact row is always the single, first answer.
        """
        _validated_institution_id(institution_id)
        with self._db.read() as cursor:
            cursor.execute(
                "SELECT course_code, title, units_min, units_max FROM cc_course_rows "
                "WHERE institution_id = ? AND course_code = ?",
                (institution_id, course_code),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return SearchHit(
            course_code=row[0],
            title=row[1],
            units_min=row[2],
            units_max=row[3],
            score=0.0,
            rank=1,
        )

    def vacuum(self) -> None:
        """Finalize: rebuild the file so its layout does not record insert order."""
        with self._db.read() as cursor:
            cursor.execute("VACUUM")
