"""The per-institution FTS5 index (implementation plan doc 04, TR 1.4).

Every test runs against a real temp SQLite file; SQLite is never faked.
"""

import sqlite3
from pathlib import Path

import pytest

import starmap.retrieval.index as index_module
from starmap.common.dbdump import canonical_dump
from starmap.common.sqlite import SqliteDatabase
from starmap.retrieval.errors import Fts5UnavailableError, InstitutionNotIndexedError
from starmap.retrieval.index import CourseIndex, compile_match_expression
from tests.retrieval.support import make_course, serialized

DE_ANZA = 113
MARIN = 20

CALCULUS_COURSES = [
    make_course(DE_ANZA, "MATH", "1A", "Calculus", 5.0),
    make_course(DE_ANZA, "MATH", "1B", "Calculus", 5.0),
    make_course(DE_ANZA, "CIS", "22C", "Data Abstraction and Structures", 4.5),
]


def sqlite_has_fts5() -> bool:
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE VIRTUAL TABLE probe USING fts5(text)")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        connection.close()


def open_index(path: Path) -> CourseIndex:
    return CourseIndex(SqliteDatabase(path))


# --- the FTS5 probe ----------------------------------------------------------


@pytest.mark.skipif(sqlite_has_fts5(), reason="this SQLite build has FTS5")
def test_construction_raises_when_sqlite_lacks_fts5(tmp_path: Path) -> None:
    with pytest.raises(Fts5UnavailableError):
        open_index(tmp_path / "corpus.db")


def test_a_failing_probe_raises_rather_than_degrades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The probe statement is monkeypatched to a bad one so the raise path is
    exercised even on SQLite builds that do have FTS5; the policy is that the
    error is NEVER caught to degrade."""
    monkeypatch.setattr(
        index_module, "FTS5_PROBE_STATEMENT", "CREATE VIRTUAL TABLE probe USING no_such_module(x)"
    )
    with pytest.raises(Fts5UnavailableError):
        open_index(tmp_path / "corpus.db")


# --- table-name safety --------------------------------------------------------


@pytest.mark.parametrize("bad_id", [0, -1])
def test_a_non_positive_institution_id_is_rejected(tmp_path: Path, bad_id: int) -> None:
    index = open_index(tmp_path / "corpus.db")
    with pytest.raises(ValueError):
        index.build(bad_id, [])
    with pytest.raises(ValueError):
        index.search(bad_id, "calculus")


# --- build -------------------------------------------------------------------


def test_build_returns_the_course_count(tmp_path: Path) -> None:
    index = open_index(tmp_path / "corpus.db")
    assert index.build(DE_ANZA, CALCULUS_COURSES) == 3


def test_a_second_build_returns_the_stored_count_and_changes_nothing(tmp_path: Path) -> None:
    """Rows regenerate only through a fresh database build, never in place."""
    path = tmp_path / "corpus.db"
    index = open_index(path)
    index.build(DE_ANZA, CALCULUS_COURSES)
    before = canonical_dump(path)

    count = index.build(DE_ANZA, CALCULUS_COURSES[:1])

    assert count == 3
    assert canonical_dump(path) == before


def test_searching_an_unbuilt_institution_raises_typed(tmp_path: Path) -> None:
    index = open_index(tmp_path / "corpus.db")
    index.build(DE_ANZA, CALCULUS_COURSES)
    with pytest.raises(InstitutionNotIndexedError) as caught:
        index.search(MARIN, "calculus")
    assert caught.value.institution_id == MARIN


# --- determinism ---------------------------------------------------------------


def test_the_same_query_twice_returns_byte_equal_results(tmp_path: Path) -> None:
    index = open_index(tmp_path / "corpus.db")
    index.build(DE_ANZA, CALCULUS_COURSES)
    assert serialized(index.search(DE_ANZA, "calculus")) == serialized(
        index.search(DE_ANZA, "calculus")
    )


def test_insert_order_of_the_input_courses_changes_nothing(tmp_path: Path) -> None:
    """Sorted-insert rule: the index is a pure function of the course SET."""
    forward = open_index(tmp_path / "forward.db")
    forward.build(DE_ANZA, CALCULUS_COURSES)
    reversed_index = open_index(tmp_path / "reversed.db")
    reversed_index.build(DE_ANZA, list(reversed(CALCULUS_COURSES)))

    assert canonical_dump(tmp_path / "forward.db") == canonical_dump(tmp_path / "reversed.db")
    assert serialized(forward.search(DE_ANZA, "calculus")) == serialized(
        reversed_index.search(DE_ANZA, "calculus")
    )


# --- per-institution isolation --------------------------------------------------


def test_building_a_second_institution_leaves_the_first_byte_identical(tmp_path: Path) -> None:
    """The TR 1.4 two-snapshots pin, transplanted: BM25 statistics must be a
    pure function of (query, institution), so another college's catalog can
    never shift this one's scores."""
    index = open_index(tmp_path / "corpus.db")
    index.build(DE_ANZA, CALCULUS_COURSES)
    before = serialized(index.search(DE_ANZA, "calculus"))

    index.build(
        MARIN,
        [
            make_course(MARIN, "MATH", "103", "Calculus", 4.0),
            make_course(MARIN, "MATH", "104", "Calculus", 4.0),
            make_course(MARIN, "MATH", "105", "Calculus with Analytic Geometry", 4.0),
            make_course(MARIN, "PHYS", "7", "Mechanics", 4.0),
        ],
    )

    assert serialized(index.search(DE_ANZA, "calculus")) == before


def test_overlapping_vocabularies_score_independently(tmp_path: Path) -> None:
    """The two institutions share the word `calculus` but with different term
    statistics; a shared FTS table would give them correlated scores."""
    index = open_index(tmp_path / "corpus.db")
    index.build(DE_ANZA, CALCULUS_COURSES)
    index.build(
        MARIN,
        [
            make_course(MARIN, "MATH", "103", "Calculus", 4.0),
            make_course(MARIN, "MATH", "104", "Calculus with Analytic Geometry", 4.0),
            make_course(MARIN, "PHYS", "7", "Mechanics", 4.0),
        ],
    )

    de_anza_scores = [hit.score for hit in index.search(DE_ANZA, "calculus")]
    marin_scores = [hit.score for hit in index.search(MARIN, "calculus")]

    assert de_anza_scores
    assert marin_scores
    assert de_anza_scores != marin_scores


# --- ordering ---------------------------------------------------------------


def test_ranks_are_contiguous_and_scores_ordered(tmp_path: Path) -> None:
    index = open_index(tmp_path / "corpus.db")
    index.build(DE_ANZA, CALCULUS_COURSES)
    hits = index.search(DE_ANZA, "calculus data structures")
    assert [hit.rank for hit in hits] == list(range(1, len(hits) + 1))
    assert [hit.score for hit in hits] == sorted((hit.score for hit in hits), reverse=True)


def test_identical_scores_break_the_tie_by_course_code(tmp_path: Path) -> None:
    index = open_index(tmp_path / "corpus.db")
    index.build(
        MARIN,
        [
            make_course(MARIN, "PE", "1B", "Hatha Yoga", 1.0),
            make_course(MARIN, "PE", "1A", "Hatha Yoga", 1.0),
        ],
    )
    hits = index.search(MARIN, "hatha yoga")
    assert hits[0].score == hits[1].score
    assert [hit.course_code for hit in hits] == ["PE 1A", "PE 1B"]


# --- match-expression compilation ---------------------------------------------


def test_the_bag_of_words_rule_quotes_and_or_joins() -> None:
    assert compile_match_expression("System-design, C++!") == '"system" OR "design" OR "c"'


def test_a_punctuation_only_query_returns_an_honest_empty_result(tmp_path: Path) -> None:
    index = open_index(tmp_path / "corpus.db")
    index.build(DE_ANZA, CALCULUS_COURSES)
    assert compile_match_expression("?!,.") == ""
    assert index.search(DE_ANZA, "?!,.") == []


def test_fts_operators_in_user_text_are_treated_as_literals(tmp_path: Path) -> None:
    """Quoting makes `NEAR`, `AND`, `OR`, `*`, and parentheses tokens, never
    syntax: the query neither raises nor gains operator semantics."""
    index = open_index(tmp_path / "corpus.db")
    index.build(DE_ANZA, CALCULUS_COURSES)
    hits = index.search(DE_ANZA, 'calculus NEAR(data) AND "structures" *')
    assert {hit.course_code for hit in hits} == {"MATH 1A", "MATH 1B", "CIS 22C"}


# --- lookup ---------------------------------------------------------------------


def test_lookup_returns_the_stored_row_or_none(tmp_path: Path) -> None:
    index = open_index(tmp_path / "corpus.db")
    index.build(DE_ANZA, CALCULUS_COURSES)
    row = index.lookup(DE_ANZA, "CIS 22C")
    assert row is not None
    assert (row.course_code, row.title, row.units_min, row.units_max) == (
        "CIS 22C",
        "Data Abstraction and Structures",
        4.5,
        4.5,
    )
    assert index.lookup(DE_ANZA, "CIS 999") is None
