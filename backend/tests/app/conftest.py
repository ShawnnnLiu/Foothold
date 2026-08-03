"""The app-test harness (doc 01, "Testing"): real fixture databases under
`tmp_path`, `TestClient` over `create_app`, zero network.

The articulation build mirrors `tests/assist/test_store.py::build`, and the
corpus index is built over the same deduped `cc_courses` projection, so these
tests exercise the exact store/index write APIs the build pipeline uses. The
committed `data/` artifacts are never opened.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from starmap.app.web.app import create_app
from starmap.app.web.config import AppConfig
from starmap.assist.normalize import (
    NormalizedAgreement,
    dedupe_course_rows,
    normalize_academic_years,
    normalize_agreement,
    normalize_institutions,
)
from starmap.assist.store import ArticulationStore
from starmap.common.sqlite import SqliteDatabase
from starmap.retrieval.index import CourseIndex

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "assist"

DE_ANZA = 113
UCSD = 7
# An institution the articulation fixture knows but the corpus never indexed.
UNINDEXED_CC = 4
MAJOR_KEY = "76/113/to/7/Major/f8d5b3e6-1d24-4b7a-9a3f-1b2c3d4e5f60"
DEPT_KEY = "76/113/to/7/Department/12"
MAJOR_LABEL = "Mathematics/Computer Science B.S."
YEAR_LABEL = "2025-2026"
# Fixture rate chosen to mirror the real UCSD ratio, so dollar assertions
# read like the verified demo numbers.
UCSD_PER_UNIT = 291.0


def _fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _normalized_agreements() -> list[NormalizedAgreement]:
    agreements = [
        normalize_agreement(
            _fixture("agreement_major_cse_cs_113_to_7_y76.json"),
            assist_key=MAJOR_KEY,
            category="major",
            label=MAJOR_LABEL,
            sending_id=DE_ANZA,
            receiving_id=UCSD,
        ),
        normalize_agreement(
            _fixture("agreement_dept_math_113_to_7_y76.json"),
            assist_key=DEPT_KEY,
            category="dept",
            label="Mathematics",
            sending_id=DE_ANZA,
            receiving_id=UCSD,
        ),
    ]
    return sorted(agreements, key=lambda item: item.agreement.assist_key)


def build_app_config(tmp_path: Path) -> AppConfig:
    """Fixture databases plus a costs file, written the way the build does."""
    items = _normalized_agreements()
    institutions, _ = normalize_institutions(_fixture("institutions.json"))
    years = normalize_academic_years(_fixture("academic_years.json"))
    cc_courses, _ = dedupe_course_rows([course for item in items for course in item.cc_courses])
    targets, _ = dedupe_course_rows([course for item in items for course in item.target_courses])

    articulation_path = tmp_path / "articulation.db"
    articulation_db = SqliteDatabase(articulation_path)
    try:
        store = ArticulationStore(articulation_db)
        store.put_institutions(institutions)
        store.put_academic_years(years)
        store.put_agreements(items)
        store.put_cc_courses(cc_courses)
        store.put_target_courses(targets)
        store.vacuum()
    finally:
        articulation_db.close()

    corpus_path = tmp_path / "corpus.db"
    corpus_db = SqliteDatabase(corpus_path)
    try:
        index = CourseIndex(corpus_db)
        index.build(DE_ANZA, cc_courses)
        index.vacuum()
    finally:
        corpus_db.close()

    costs_path = tmp_path / "costs.json"
    costs_path.write_text(
        json.dumps(
            {
                "version": "costs-v1",
                "sources": [
                    {
                        "url": "https://example.test/costs",
                        "note": "app-test fixture rates",
                        "retrieved": "2026-08-03",
                    }
                ],
                "cc_per_unit_default": 46.0,
                "target_per_unit": {str(UCSD): UCSD_PER_UNIT},
            }
        ),
        encoding="utf-8",
    )

    return AppConfig(
        articulation_db=articulation_path,
        corpus_db=corpus_path,
        sessions_db=tmp_path / "sessions.db",
        costs_path=costs_path,
        dist_dir=tmp_path / "dist",
        secure_cookies=False,
    )


def demo_body() -> dict[str, Any]:
    """The fixture student: clean matches, one half-series (MATH 1C without
    MATH 1D), and one code outside the vocabulary."""
    return {
        "sending_institution_id": DE_ANZA,
        "receiving_institution_id": UCSD,
        "major_key": MAJOR_KEY,
        "courses": [
            {"course_code": "MATH 1A"},
            {"course_code": "MATH 1B"},
            {"course_code": "MATH 1C"},
            {"course_code": "CIS 36B"},
            {"course_code": "CIS 22C"},
            {"course_code": "PHYS 4A"},
        ],
    }


@pytest.fixture
def app_config(tmp_path: Path) -> AppConfig:
    return build_app_config(tmp_path)


@pytest.fixture
def app(app_config: AppConfig) -> FastAPI:
    return create_app(app_config)


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)
