"""The build script, end to end and offline.

The cache is real: this seeds a temp directory with the exact url-hash
filenames `AssistFetcher` looks for, then runs the whole pipeline over it with
no transport involved at all, because an offline fetcher answers every url from
disk. That is the same code path `make build-data` takes.

The corridor is narrowed to the demo pair with a two-report reports list rather
than the real 168 majors, so the fixture pair drives the walk, the normalizer,
the store, and the report in one pass.
"""

import argparse
import importlib.util
import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from starmap.assist.corridor import (
    academic_years_url,
    agreement_url,
    agreements_url,
    categories_url,
    institutions_url,
)
from starmap.assist.fetch import cache_key
from starmap.common.dbdump import canonical_dump

BACKEND_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_ROOT / "scripts" / "build_articulation.py"
FIXTURES = BACKEND_ROOT / "tests" / "fixtures" / "assist"

MAJOR_KEY = "76/113/to/7/Major/f8d5b3e6-1d24-4b7a-9a3f-1b2c3d4e5f60"
DEPT_KEY = "76/113/to/7/Department/12"
DE_ANZA = 113
UCSD = 7
YEAR = 76
DEMO_PAIR = (DE_ANZA, UCSD)


def load_script() -> Any:
    """`scripts/` is not an importable package, so load the module by path."""
    spec = importlib.util.spec_from_file_location("build_articulation", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_articulation = load_script()


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def reports_payload(label: str, key: str) -> bytes:
    return json.dumps({"reports": [{"label": label, "key": key}], "allReports": []}).encode()


@pytest.fixture
def cache_dir(tmp_path: Path) -> Path:
    """A cache holding exactly what a demo-pair walk asks for."""
    directory = tmp_path / "raw"
    directory.mkdir()
    entries = {
        academic_years_url(): fixture_bytes("academic_years.json"),
        institutions_url(): fixture_bytes("institutions.json"),
        categories_url(UCSD, DE_ANZA, YEAR): fixture_bytes("categories_113_to_7_y76.json"),
        agreements_url(UCSD, DE_ANZA, YEAR, "major"): reports_payload(
            "Mathematics/Computer Science B.S.", MAJOR_KEY
        ),
        agreements_url(UCSD, DE_ANZA, YEAR, "dept"): reports_payload("Mathematics", DEPT_KEY),
        agreement_url(MAJOR_KEY): fixture_bytes("agreement_major_cse_cs_113_to_7_y76.json"),
        agreement_url(DEPT_KEY): fixture_bytes("agreement_dept_math_113_to_7_y76.json"),
    }
    for url, body in entries.items():
        (directory / f"{cache_key(url)}.json").write_bytes(body)
    return directory


def run(stage: str, cache_dir: Path, tmp_path: Path, **kwargs: Any) -> tuple[int, Path, Path]:
    db_path = tmp_path / "articulation.db"
    report_path = tmp_path / "reports" / "assist_build_report.json"
    code = build_articulation.run_build(
        stage=stage,
        cache_dir=cache_dir,
        db_path=db_path,
        report_path=report_path,
        only_pair=DEMO_PAIR,
        **kwargs,
    )
    return code, db_path, report_path


# --- the stages -------------------------------------------------------------


def test_stage_all_writes_the_artifact_and_the_report(cache_dir: Path, tmp_path: Path) -> None:
    code, db_path, report_path = run("all", cache_dir, tmp_path)
    assert code == 0
    assert db_path.exists()
    document = json.loads(report_path.read_text(encoding="utf-8"))
    assert document["totals"]["agreements_stored"] == 2
    assert document["totals"]["agreements_excluded"] == 0
    assert document["totals"]["articulations_excluded"] == 0
    assert document["totals"]["institution_kind_unknown"] == 33


def test_the_store_stage_also_writes_the_committed_gzip(cache_dir: Path, tmp_path: Path) -> None:
    """The COMMITTED artifact is the gzip, not the database: GitHub rejects
    files over 100 MB and the corridor build is roughly twice that."""
    _, db_path, _ = run("all", cache_dir, tmp_path)
    packed = db_path.with_suffix(".db.gz")

    assert packed.exists()
    assert packed.stat().st_size < db_path.stat().st_size


def test_unpacking_the_gzip_restores_the_database_byte_for_byte(
    cache_dir: Path, tmp_path: Path
) -> None:
    """`make unpack-data` is the only way a fresh clone gets a database, since
    rebuilding needs the 2 GB raw cache that is not committed."""
    _, db_path, _ = run("all", cache_dir, tmp_path)
    original = db_path.read_bytes()
    db_path.unlink()

    restored = build_articulation.unpack_database(db_path)

    assert restored.read_bytes() == original


def test_packing_is_a_pure_function_of_the_database(cache_dir: Path, tmp_path: Path) -> None:
    """`mtime=0`: two packs of one database agree, so a rebuild that changed
    nothing does not show up as a 25 MB diff."""
    _, db_path, _ = run("all", cache_dir, tmp_path)
    first = db_path.with_suffix(".db.gz").read_bytes()

    second = build_articulation.pack_database(db_path).read_bytes()

    assert first == second


def test_check_does_not_pack_its_throwaway_rebuild(cache_dir: Path, tmp_path: Path) -> None:
    """Identity is compared over canonical dumps, never over compressed bytes,
    so gzipping a temp build that is deleted moments later buys nothing."""
    code, _, _ = run("all", cache_dir, tmp_path)
    assert code == 0
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    build_articulation.run_build(
        stage="store",
        cache_dir=cache_dir,
        db_path=scratch / "articulation.db",
        report_path=scratch / "report.json",
        only_pair=DEMO_PAIR,
        pack=False,
    )

    assert not (scratch / "articulation.db.gz").exists()


def test_the_built_artifact_holds_the_demo_pairs_rows(cache_dir: Path, tmp_path: Path) -> None:
    _, db_path, _ = run("all", cache_dir, tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        counts = {
            table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            for table in ("agreements", "articulations", "agreement_requirements", "institutions")
        }
    finally:
        connection.close()
    assert counts == {
        "agreements": 2,
        "articulations": 19,
        "agreement_requirements": 4,
        "institutions": 148,
    }


def test_stage_fetch_touches_neither_artifact(cache_dir: Path, tmp_path: Path) -> None:
    code, db_path, report_path = run("fetch", cache_dir, tmp_path)
    assert code == 0
    assert not db_path.exists()
    assert not report_path.exists()


def test_stage_normalize_writes_the_report_but_no_database(cache_dir: Path, tmp_path: Path) -> None:
    code, db_path, report_path = run("normalize", cache_dir, tmp_path)
    assert code == 0
    assert report_path.exists()
    assert not db_path.exists()


def test_one_broken_payload_is_excluded_and_the_build_completes(
    cache_dir: Path, tmp_path: Path
) -> None:
    """The build's whole posture: a failing agreement is excluded and reported,
    never allowed to break the build."""
    payload = json.loads(fixture_bytes("agreement_dept_math_113_to_7_y76.json"))
    payload["isSuccessful"] = False
    (cache_dir / f"{cache_key(agreement_url(DEPT_KEY))}.json").write_text(json.dumps(payload))

    code, db_path, report_path = run("all", cache_dir, tmp_path)
    assert code == 0
    document = json.loads(report_path.read_text(encoding="utf-8"))
    assert document["totals"]["agreements_stored"] == 1
    (pair,) = document["pairs"]
    assert [entry["reason_code"] for entry in pair["agreements_excluded"]] == ["envelope_invalid"]
    assert [entry["assist_key"] for entry in pair["agreements_excluded"]] == [DEPT_KEY]

    connection = sqlite3.connect(db_path)
    try:
        stored = connection.execute("SELECT assist_key FROM agreements").fetchall()
    finally:
        connection.close()
    assert stored == [(MAJOR_KEY,)]


def test_an_offline_run_with_a_cold_cache_fails_typed(tmp_path: Path) -> None:
    """No network fallback: a missing payload is an `agreement_fetch_failed`,
    not a live request."""
    empty = tmp_path / "cold"
    empty.mkdir()
    with pytest.raises(Exception) as caught:
        run("all", empty, tmp_path)
    assert "offline mode" in str(caught.value)


# --- determinism and the --check gate ---------------------------------------


def test_two_builds_from_one_cache_are_identical(cache_dir: Path, tmp_path: Path) -> None:
    _, first_db, first_report = run("all", cache_dir, tmp_path / "first")
    _, second_db, second_report = run("all", cache_dir, tmp_path / "second")
    assert canonical_dump(first_db) == canonical_dump(second_db)
    assert first_report.read_bytes() == second_report.read_bytes()


def test_check_passes_on_a_freshly_built_artifact(
    cache_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, db_path, report_path = run("all", cache_dir, tmp_path)
    code = build_articulation.run_check(
        cache_dir=cache_dir, db_path=db_path, report_path=report_path, only_pair=DEMO_PAIR
    )
    assert code == 0
    assert "regenerate identically" in capsys.readouterr().out


def test_check_fails_after_a_row_is_mutated(
    cache_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, db_path, report_path = run("all", cache_dir, tmp_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("DELETE FROM articulations WHERE position = 0")
        connection.commit()
    finally:
        connection.close()
    code = build_articulation.run_check(
        cache_dir=cache_dir, db_path=db_path, report_path=report_path, only_pair=DEMO_PAIR
    )
    assert code == 1
    assert f"out of date: {db_path}" in capsys.readouterr().out


def test_check_fails_after_the_report_is_edited(
    cache_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The report is a committed artifact too, so hand-editing it must fail the
    same gate the database does."""
    _, db_path, report_path = run("all", cache_dir, tmp_path)
    document = json.loads(report_path.read_text(encoding="utf-8"))
    document["totals"]["agreements_stored"] = 99
    report_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    code = build_articulation.run_check(
        cache_dir=cache_dir, db_path=db_path, report_path=report_path, only_pair=DEMO_PAIR
    )
    assert code == 1
    assert f"out of date: {report_path}" in capsys.readouterr().out


def test_check_reports_a_missing_artifact(
    cache_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = build_articulation.run_check(
        cache_dir=cache_dir,
        db_path=tmp_path / "absent.db",
        report_path=tmp_path / "absent.json",
        only_pair=DEMO_PAIR,
    )
    assert code == 1
    assert "missing:" in capsys.readouterr().out


def test_a_rebuild_never_merges_into_an_older_artifact(cache_dir: Path, tmp_path: Path) -> None:
    """A stale row surviving a rebuild would break identity silently."""
    _, db_path, _ = run("all", cache_dir, tmp_path)
    before = canonical_dump(db_path)
    connection = sqlite3.connect(db_path)
    try:
        connection.execute(
            "INSERT INTO cc_courses (institution_id, course_code, payload) VALUES (?, ?, ?)",
            (999, "GHOST 1", "{}"),
        )
        connection.commit()
    finally:
        connection.close()
    run("all", cache_dir, tmp_path)
    assert canonical_dump(db_path) == before


# --- the command line -------------------------------------------------------


def test_the_pair_flag_parses_sending_and_receiving_ids() -> None:
    assert build_articulation.parse_pair("113:7") == DEMO_PAIR


@pytest.mark.parametrize("value", ["113", "113:", "a:b", "113/7"])
def test_a_malformed_pair_flag_is_rejected(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        build_articulation.parse_pair(value)


@pytest.mark.parametrize("stage", ["normalize", "store"])
def test_allow_network_cannot_reach_the_network_from_the_later_stages(
    stage: str, tmp_path: Path
) -> None:
    """`normalize` and `store` are pure functions of the cache by construction,
    not by discipline: even under `--allow-network` a cold cache fails typed
    rather than issuing a live request."""
    cold = tmp_path / "cold"
    cold.mkdir()
    with pytest.raises(Exception) as caught:
        run(stage, cold, tmp_path, allow_network=True)
    assert "offline mode" in str(caught.value)
