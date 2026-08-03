"""The fixed-threshold resolver, pinned by the fixture case file.

`backend/tests/fixtures/retrieval/resolve_cases.json` is the ground truth for
the threshold semantics: exact, else fuzzy at or above 0.6, else unresolved.
"""

from pathlib import Path
from typing import Any

import pytest

from starmap.retrieval.index import CourseIndex
from starmap.retrieval.resolve import (
    FUZZY_ACCEPT_RATIO,
    FUZZY_CANDIDATES_K,
    resolve_course,
)
from tests.retrieval.support import build_fixture_index, load_resolve_fixture

FIXTURE = load_resolve_fixture()
CASES: list[dict[str, Any]] = FIXTURE["cases"]

DE_ANZA = 113


@pytest.fixture(scope="module")
def index(tmp_path_factory: pytest.TempPathFactory) -> CourseIndex:
    return build_fixture_index(tmp_path_factory.mktemp("resolve") / "corpus.db")


def test_the_locked_constants_are_the_spec_values() -> None:
    assert FUZZY_ACCEPT_RATIO == 0.6
    assert FUZZY_CANDIDATES_K == 5


@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_fixture_case(index: CourseIndex, case: dict[str, Any]) -> None:
    resolution = resolve_course(
        index, case["institution_id"], code=case["code"], title=case["title"]
    )
    assert resolution.status == case["expected_status"]
    assert resolution.course_code == case["expected_course_code"]


def test_an_exact_resolution_carries_the_row_and_no_ratio(index: CourseIndex) -> None:
    resolution = resolve_course(index, DE_ANZA, code="MATH 1A", title=None)
    assert resolution.status == "exact"
    assert (resolution.title, resolution.units_min, resolution.units_max) == ("Calculus", 5.0, 5.0)
    assert resolution.ratio is None


def test_a_fuzzy_resolution_carries_the_hit_and_its_ratio(index: CourseIndex) -> None:
    resolution = resolve_course(index, DE_ANZA, code=None, title="diferential equations")
    assert resolution.status == "fuzzy_match"
    assert resolution.title == "Differential Equations"
    assert resolution.ratio is not None
    assert resolution.ratio >= FUZZY_ACCEPT_RATIO


def test_unresolved_with_candidates_still_reports_the_best_ratio(index: CourseIndex) -> None:
    resolution = resolve_course(index, DE_ANZA, code="MTH 2A", title=None)
    assert resolution.status == "unresolved"
    assert resolution.course_code is None
    assert resolution.ratio is not None
    assert 0.0 < resolution.ratio < FUZZY_ACCEPT_RATIO


def test_unresolved_with_no_candidates_has_no_ratio(index: CourseIndex) -> None:
    resolution = resolve_course(index, DE_ANZA, code="zzzz", title="qqqq wwww")
    assert resolution.status == "unresolved"
    assert resolution.ratio is None


def test_identical_calls_return_equal_resolutions(index: CourseIndex) -> None:
    first = resolve_course(index, DE_ANZA, code="MTH 2A", title="Differential Equations")
    second = resolve_course(index, DE_ANZA, code="MTH 2A", title="Differential Equations")
    assert first == second


def test_every_fixture_case_name_is_unique() -> None:
    names = [case["name"] for case in CASES]
    assert len(names) == len(set(names))


def test_the_fixture_file_lives_where_the_plan_says() -> None:
    """Doc 04 names the path; a moved fixture would silently stop pinning."""
    expected = Path(__file__).resolve().parents[1] / "fixtures" / "retrieval" / "resolve_cases.json"
    assert expected.exists()
