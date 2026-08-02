"""`articulation.db`: the committed, read-only articulation artifact.

Responsibility split (TR 1.1): the tables hold canonical contract JSON in a
`payload` column and every read re-validates it through the contract, so a
payload that drifted from its model fails at read time instead of flowing into
an evaluation. The structured columns beside each payload exist only for the
lookups the evaluator makes (by pair, by agreement, by institution).

The artifact is committed, so identity is what the write discipline is FOR:

- every insert is issued in a deterministic order (institutions by `assist_id`,
  years by `year_id`, agreements by `assist_key`, articulations and
  requirements by `(agreement_id, position)`, both projections by
  `(institution_id, course_code)`);
- no timestamps anywhere, so two builds of the same cache are equal;
- `VACUUM` before finalizing, so the page layout does not depend on the order
  rows happened to arrive in.

`canonical_dump` is what actually defines identity (raw bytes vary across
SQLite library versions), and `make build-check` compares dumps.

The latest published year for a pair is DERIVED at read time as `MAX(academic_
year_id)` over that pair's agreements rather than stored: a second table
recording it could disagree with the agreements themselves.
"""

from collections.abc import Iterable, Sequence
from typing import Any

from starmap.assist.normalize import AcademicYear, NormalizedAgreement
from starmap.common.sqlite import SqliteDatabase, ensure_schema
from starmap.contracts.agreement import Agreement, RequirementGroupAsset
from starmap.contracts.articulation import Articulation
from starmap.contracts.cc_course import CcCourse
from starmap.contracts.institution import Institution
from starmap.contracts.target_course import TargetCourse

COMPONENT = "articulation"
SCHEMA_VERSION = 1

SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS institutions (
        assist_id INTEGER PRIMARY KEY, payload TEXT NOT NULL)
    """,
    """
    CREATE TABLE IF NOT EXISTS academic_years (
        year_id INTEGER PRIMARY KEY, label TEXT NOT NULL, fall_year INTEGER NOT NULL)
    """,
    """
    CREATE TABLE IF NOT EXISTS agreements (
        agreement_id TEXT PRIMARY KEY, assist_key TEXT NOT NULL UNIQUE,
        sending_institution_id INTEGER NOT NULL, receiving_institution_id INTEGER NOT NULL,
        academic_year_id INTEGER NOT NULL, category TEXT NOT NULL, payload TEXT NOT NULL)
    """,
    """
    CREATE TABLE IF NOT EXISTS articulations (
        agreement_id TEXT NOT NULL, position INTEGER NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY (agreement_id, position))
    """,
    """
    CREATE TABLE IF NOT EXISTS agreement_requirements (
        agreement_id TEXT NOT NULL, position INTEGER NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY (agreement_id, position))
    """,
    """
    CREATE TABLE IF NOT EXISTS cc_courses (
        institution_id INTEGER NOT NULL, course_code TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY (institution_id, course_code))
    """,
    """
    CREATE TABLE IF NOT EXISTS target_courses (
        institution_id INTEGER NOT NULL, course_code TEXT NOT NULL, payload TEXT NOT NULL,
        PRIMARY KEY (institution_id, course_code))
    """,
)


class ArticulationStore:
    """Writes and reads `articulation.db`. Writes happen once, at build time."""

    def __init__(self, db: SqliteDatabase) -> None:
        self._db = db
        ensure_schema(db, COMPONENT, version=SCHEMA_VERSION, statements=SCHEMA_STATEMENTS)

    # --- writes -------------------------------------------------------------

    def put_institutions(self, institutions: Iterable[Institution]) -> None:
        rows = sorted(institutions, key=lambda item: item.assist_id)
        with self._db.transaction() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO institutions (assist_id, payload) VALUES (?, ?)",
                [(item.assist_id, item.model_dump_json()) for item in rows],
            )

    def put_academic_years(self, years: Iterable[AcademicYear]) -> None:
        rows = sorted(years, key=lambda year: year.year_id)
        with self._db.transaction() as cursor:
            cursor.executemany(
                "INSERT OR REPLACE INTO academic_years (year_id, label, fall_year) "
                "VALUES (?, ?, ?)",
                [(year.year_id, year.label, year.fall_year) for year in rows],
            )

    def put_agreements(self, agreements: Iterable[NormalizedAgreement]) -> None:
        """Agreements with their articulations and requirement groups.

        The projections are NOT written here: they dedupe across every
        agreement in the build, so they have their own single write.
        """
        ordered = sorted(agreements, key=lambda item: item.agreement.assist_key)
        with self._db.transaction() as cursor:
            for normalized in ordered:
                agreement = normalized.agreement
                cursor.execute(
                    "INSERT OR REPLACE INTO agreements (agreement_id, assist_key, "
                    "sending_institution_id, receiving_institution_id, academic_year_id, "
                    "category, payload) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        agreement.agreement_id,
                        agreement.assist_key,
                        agreement.sending_institution_id,
                        agreement.receiving_institution_id,
                        agreement.academic_year_id,
                        agreement.category,
                        agreement.model_dump_json(),
                    ),
                )
                cursor.executemany(
                    "INSERT OR REPLACE INTO articulations (agreement_id, position, payload) "
                    "VALUES (?, ?, ?)",
                    [
                        (agreement.agreement_id, item.position, item.model_dump_json())
                        for item in sorted(normalized.articulations, key=lambda a: a.position)
                    ],
                )
                cursor.executemany(
                    "INSERT OR REPLACE INTO agreement_requirements "
                    "(agreement_id, position, payload) VALUES (?, ?, ?)",
                    [
                        (agreement.agreement_id, group.position, group.model_dump_json())
                        for group in sorted(normalized.requirement_groups, key=lambda g: g.position)
                    ],
                )

    def put_cc_courses(self, courses: Iterable[CcCourse]) -> None:
        self._put_projection("cc_courses", courses)

    def put_target_courses(self, courses: Iterable[TargetCourse]) -> None:
        self._put_projection("target_courses", courses)

    def _put_projection(self, table: str, courses: Iterable[CcCourse | TargetCourse]) -> None:
        """`table` is one of this module's two literal projection table names,
        never anything a caller composes, so the interpolation stays closed."""
        rows = sorted(courses, key=lambda course: (course.institution_id, course.course_code))
        with self._db.transaction() as cursor:
            cursor.executemany(
                f"INSERT OR REPLACE INTO {table} (institution_id, course_code, payload) "
                "VALUES (?, ?, ?)",
                [
                    (course.institution_id, course.course_code, course.model_dump_json())
                    for course in rows
                ],
            )

    def vacuum(self) -> None:
        """Finalize: rebuild the file so its layout does not record insert order."""
        with self._db.read() as cursor:
            cursor.execute("VACUUM")

    # --- reads (increments 6-7) ---------------------------------------------

    def load_institutions(self) -> list[Institution]:
        return [
            Institution.model_validate_json(payload)
            for (payload,) in self._rows("SELECT payload FROM institutions ORDER BY assist_id")
        ]

    def load_academic_years(self) -> list[AcademicYear]:
        return [
            AcademicYear(year_id=year_id, label=label, fall_year=fall_year)
            for year_id, label, fall_year in self._rows(
                "SELECT year_id, label, fall_year FROM academic_years ORDER BY year_id"
            )
        ]

    def load_agreements_for_pair(self, sending_id: int, receiving_id: int) -> list[Agreement]:
        return [
            Agreement.model_validate_json(payload)
            for (payload,) in self._rows(
                "SELECT payload FROM agreements WHERE sending_institution_id = ? "
                "AND receiving_institution_id = ? ORDER BY assist_key",
                (sending_id, receiving_id),
            )
        ]

    def latest_year_for_pair(self, sending_id: int, receiving_id: int) -> int | None:
        """Derived, never stored: the newest year this pair has an agreement in."""
        rows = self._rows(
            "SELECT MAX(academic_year_id) FROM agreements WHERE sending_institution_id = ? "
            "AND receiving_institution_id = ?",
            (sending_id, receiving_id),
        )
        year_id = rows[0][0]
        return int(year_id) if year_id is not None else None

    def load_articulations(self, agreement_id: str) -> list[Articulation]:
        return [
            Articulation.model_validate_json(payload)
            for (payload,) in self._rows(
                "SELECT payload FROM articulations WHERE agreement_id = ? ORDER BY position",
                (agreement_id,),
            )
        ]

    def load_requirements(self, agreement_id: str) -> list[RequirementGroupAsset]:
        return [
            RequirementGroupAsset.model_validate_json(payload)
            for (payload,) in self._rows(
                "SELECT payload FROM agreement_requirements WHERE agreement_id = ? "
                "ORDER BY position",
                (agreement_id,),
            )
        ]

    def load_cc_courses(self, institution_id: int) -> list[CcCourse]:
        return [
            CcCourse.model_validate_json(payload)
            for (payload,) in self._rows(
                "SELECT payload FROM cc_courses WHERE institution_id = ? ORDER BY course_code",
                (institution_id,),
            )
        ]

    def load_target_courses(self, institution_id: int) -> list[TargetCourse]:
        return [
            TargetCourse.model_validate_json(payload)
            for (payload,) in self._rows(
                "SELECT payload FROM target_courses WHERE institution_id = ? ORDER BY course_code",
                (institution_id,),
            )
        ]

    def _rows(self, sql: str, parameters: Sequence[object] = ()) -> list[Any]:
        """Raw rows. Every payload row is re-validated by its caller, which is
        where the untyped SQLite boundary becomes typed again."""
        with self._db.read() as cursor:
            cursor.execute(sql, tuple(parameters))
            return cursor.fetchall()
