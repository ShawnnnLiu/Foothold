import shutil
import subprocess
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = BACKEND_ROOT / "scripts" / "generate_schemas.py"
SCHEMAS_DIR = BACKEND_ROOT / "schemas"

EXPECTED_CONTRACTS = {
    "agreement",
    "arbitrage",
    "articulation",
    "articulation_expr",
    "cc_course",
    "evaluation",
    "institution",
    "llm_call_log",
    "target_course",
}


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def schema_files(directory: Path) -> dict[str, bytes]:
    return {path.name: path.read_bytes() for path in directory.glob("*.schema.json")}


def test_every_registered_contract_has_a_committed_schema() -> None:
    committed = {path.stem.removesuffix(".schema") for path in SCHEMAS_DIR.glob("*.schema.json")}
    assert committed == EXPECTED_CONTRACTS


def test_check_passes_on_committed_schemas() -> None:
    result = run_script("--check")
    assert result.returncode == 0, result.stdout + result.stderr


def test_write_twice_is_deterministic(tmp_path: Path) -> None:
    first_dir = tmp_path / "first"
    second_dir = tmp_path / "second"
    assert run_script("--schemas-dir", str(first_dir)).returncode == 0
    assert run_script("--schemas-dir", str(second_dir)).returncode == 0

    first = schema_files(first_dir)
    second = schema_files(second_dir)
    assert first == second
    assert {name.removesuffix(".schema.json") for name in first} == EXPECTED_CONTRACTS


def test_check_detects_drift_and_missing(tmp_path: Path) -> None:
    working = tmp_path / "schemas"
    shutil.copytree(SCHEMAS_DIR, working)

    mutated = working / "institution.schema.json"
    mutated.write_text(mutated.read_text() + " ")
    result = run_script("--check", "--schemas-dir", str(working))
    assert result.returncode == 1
    assert "out of date:" in result.stdout

    mutated.unlink()
    result = run_script("--check", "--schemas-dir", str(working))
    assert result.returncode == 1
    assert "missing:" in result.stdout
