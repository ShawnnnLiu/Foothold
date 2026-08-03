"""The milestone CLI, end to end and offline: a temp `articulation.db` built
from the captured ASSIST fixtures through the real build pipeline, then one
`evaluate_student.py` run over it, asserting the demo shape renders and the
process exits 0."""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from starmap.app.web.errors import UnknownAgreementError
from starmap.assist.corridor import (
    academic_years_url,
    agreement_url,
    agreements_url,
    categories_url,
    institutions_url,
)
from starmap.assist.fetch import cache_key

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = BACKEND_ROOT / "scripts"
FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "assist"

MAJOR_KEY = "76/113/to/7/Major/f8d5b3e6-1d24-4b7a-9a3f-1b2c3d4e5f60"
DEPT_KEY = "76/113/to/7/Department/12"
DE_ANZA = 113
UCSD = 7
YEAR = 76


def load_script(name: str) -> Any:
    """`scripts/` is not an importable package, so load modules by path."""
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_articulation = load_script("build_articulation")
evaluate_student = load_script("evaluate_student")


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    """A real artifact built offline from the captured demo-pair fixtures."""
    cache_dir = tmp_path / "raw"
    cache_dir.mkdir()
    reports = {
        "major": {"label": "CSE: Computer Science B.S.", "key": MAJOR_KEY},
        "dept": {"label": "Mathematics", "key": DEPT_KEY},
    }
    entries = {
        academic_years_url(): (FIXTURES / "academic_years.json").read_bytes(),
        institutions_url(): (FIXTURES / "institutions.json").read_bytes(),
        categories_url(UCSD, DE_ANZA, YEAR): (
            FIXTURES / "categories_113_to_7_y76.json"
        ).read_bytes(),
        agreements_url(UCSD, DE_ANZA, YEAR, "major"): json.dumps(
            {"reports": [reports["major"]], "allReports": []}
        ).encode(),
        agreements_url(UCSD, DE_ANZA, YEAR, "dept"): json.dumps(
            {"reports": [reports["dept"]], "allReports": []}
        ).encode(),
        agreement_url(MAJOR_KEY): (
            FIXTURES / "agreement_major_cse_cs_113_to_7_y76.json"
        ).read_bytes(),
        agreement_url(DEPT_KEY): (FIXTURES / "agreement_dept_math_113_to_7_y76.json").read_bytes(),
    }
    for url, body in entries.items():
        (cache_dir / f"{cache_key(url)}.json").write_bytes(body)
    path = tmp_path / "articulation.db"
    code = build_articulation.run_build(
        stage="all",
        cache_dir=cache_dir,
        db_path=path,
        corpus_path=tmp_path / "corpus.db",
        report_path=tmp_path / "reports" / "assist_build_report.json",
        only_pair=(DE_ANZA, UCSD),
    )
    assert code == 0
    return path


@pytest.fixture
def student_path(tmp_path: Path) -> Path:
    path = tmp_path / "student.json"
    path.write_text(
        json.dumps(
            {
                "version": "demo-student-v1",
                "comment": "CLI test student",
                "courses": [
                    {"course_code": "CIS 22C", "units": 4.5},
                    {"course_code": "MATH 1C", "units": 5.0},
                    {"course_code": "BIO 999", "units": 4.0},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


@pytest.fixture
def costs_path(tmp_path: Path) -> Path:
    path = tmp_path / "costs.json"
    path.write_text(
        json.dumps(
            {
                "version": "costs-v1",
                "sources": [
                    {
                        "url": "https://example.edu/fees",
                        "note": "test-only figures",
                        "retrieved": "2026-08-02",
                    }
                ],
                "cc_per_unit_default": 46.0,
                "target_per_unit": {"7": 100.0},
            }
        ),
        encoding="utf-8",
    )
    return path


def test_cli_renders_the_board_and_exits_zero(
    db_path: Path,
    student_path: Path,
    costs_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = evaluate_student.main(
        [
            "--db",
            str(db_path),
            "--student",
            str(student_path),
            "--costs",
            str(costs_path),
            "--sending",
            str(DE_ANZA),
            "--receiving",
            str(UCSD),
            "--major-key",
            MAJOR_KEY,
        ]
    )
    output = capsys.readouterr().out
    assert code == 0
    # CIS 22C satisfies CSE 12's honors-or-regular Or; MATH 1C alone is half
    # the MATH 20C series; BIO 999 is not in the De Anza vocabulary.
    assert "[transfers_clean] CIS 22C -> CSE 12" in output
    assert "[partial_series] MATH 1C ->" in output
    assert "[unresolved] BIO 999" in output
    assert "REQUIREMENTS STILL OWED" in output
    assert "cite: " + MAJOR_KEY in output
    assert "Data: ASSIST.org" in output


def test_cli_rejects_an_unknown_major_key(db_path: Path, student_path: Path) -> None:
    # Typed since the F1 bundles move: the shared loader raises the same
    # message as the old ValueError, as the 409 precondition error.
    with pytest.raises(UnknownAgreementError, match="no agreement with key"):
        evaluate_student.run(
            db_path=db_path,
            student_path=student_path,
            costs_path=None,
            sending=DE_ANZA,
            receiving=UCSD,
            major_key="76/113/to/7/Major/00000000-0000-0000-0000-000000000000",
        )
