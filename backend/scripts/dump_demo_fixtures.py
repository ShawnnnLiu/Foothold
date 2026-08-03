"""Dump the cross-language parity fixtures for the frontend (doc 02).

Runs the committed demo student through `load_bundle` + `build_evaluation` +
`build_triage_board` with a fixed clock and a fixed evaluation id, and writes
`frontend/src/lib/__fixtures__/evaluation.demo.json` and `board.demo.json`.
The vitest parity test pins `buildTriageBoard(evaluation.demo.json)` against
`board.demo.json`, so `lib/evaluation.ts` and `transfer/triage.py` never
drift.

Course requests are built exactly the way `POST /api/evaluations` builds them
(projection `units_min` and title; client units are never trusted), so the
evaluation fixture is byte-representative of the real wire response.

Output bytes are `json.dumps(payload, indent=2, sort_keys=True) + "\\n"` (the
repo's byte-determinism recipe, TR 4.5). `--check` recomputes and exits
non-zero listing `missing:` / `out of date:` files.

`make check` runs `--check` on clones without `data/articulation.db` (CI
never runs `make unpack-data`), so a missing database is restored from the
committed gzip first: offline, deterministic, and idempotent.
"""

import argparse
import gzip
import json
import shutil
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from starmap.app.web.bundles import load_bundle
from starmap.assist.store import ArticulationStore
from starmap.common.sqlite import SqliteDatabase
from starmap.transfer.costs import load_cost_table
from starmap.transfer.evaluate import CourseRequest, build_evaluation
from starmap.transfer.triage import CREDIT_BUCKETS, TriageBoard, build_triage_board

REPO_ROOT = Path(__file__).resolve().parents[2]
DB_PATH = REPO_ROOT / "data" / "articulation.db"
STUDENT_PATH = REPO_ROOT / "data" / "curated" / "demo_students" / "deanza_ucsd_cs.json"
COSTS_PATH = REPO_ROOT / "data" / "curated" / "costs.json"
FIXTURES_DIR = REPO_ROOT / "frontend" / "src" / "lib" / "__fixtures__"

STUDENT_FILE_VERSION = "demo-student-v1"

# The committed demo pair (docs/notes/evaluator_verification.md).
SENDING_ID = 113
RECEIVING_ID = 7
MAJOR_KEY = "76/113/to/7/Major/d2dfb7a8-d505-4e70-f33c-08ddd3b241a4"

FIXED_NOW = datetime(2026, 8, 3, tzinfo=UTC)
FIXED_ID_HEX = "0" * 16


class FixedClock:
    """Byte-stable stand-in for `common.clock.Clock`."""

    def now(self) -> datetime:
        return FIXED_NOW

    def monotonic(self) -> float:
        return 0.0


class FixedIdGenerator:
    """Byte-stable stand-in for `common.ids.IdGenerator`."""

    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{FIXED_ID_HEX}"


def ensure_database(db_path: Path) -> None:
    """Restore the artifact from its committed gzip when it is absent."""
    if db_path.exists():
        return
    packed = db_path.with_suffix(db_path.suffix + ".gz")
    if not packed.exists():
        raise FileNotFoundError(f"neither {db_path} nor {packed} exists")
    with gzip.open(packed, "rb") as raw, db_path.open("wb") as out:
        shutil.copyfileobj(raw, out)


def load_demo_codes(path: Path) -> list[str]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("version") != STUDENT_FILE_VERSION:
        raise ValueError(
            f"student file {path} has version {document.get('version')!r}, "
            f"expected {STUDENT_FILE_VERSION!r}"
        )
    return [entry["course_code"] for entry in document["courses"]]


def board_payload(board: TriageBoard) -> dict[str, object]:
    """The board as the exact JSON shape `lib/evaluation.ts` produces."""
    return {
        "columns": {
            bucket.value: [finding.model_dump(mode="json") for finding in board.columns[bucket]]
            for bucket in CREDIT_BUCKETS
        },
        "still_owed": [finding.model_dump(mode="json") for finding in board.still_owed],
        "header": asdict(board.header),
    }


def render_fixtures() -> dict[str, str]:
    """File name -> exact bytes, via the repo's byte-determinism recipe."""
    ensure_database(DB_PATH)
    store = ArticulationStore(SqliteDatabase(DB_PATH))
    bundle = load_bundle(store, SENDING_ID, RECEIVING_ID, MAJOR_KEY)
    projection = {row.course_code: row for row in store.load_cc_courses(SENDING_ID)}
    requests = [
        CourseRequest(course_code=code, units=row.units_min, title=row.title)
        if (row := projection.get(code)) is not None
        else CourseRequest(course_code=code)
        for code in load_demo_codes(STUDENT_PATH)
    ]
    evaluation = build_evaluation(
        requests=requests,
        vocabulary=frozenset(projection),
        bundle=bundle,
        id_generator=FixedIdGenerator(),
        clock=FixedClock(),
        cost_table=load_cost_table(COSTS_PATH),
    )
    board = build_triage_board(evaluation)
    return {
        "evaluation.demo.json": json.dumps(
            evaluation.model_dump(mode="json"), indent=2, sort_keys=True
        )
        + "\n",
        "board.demo.json": json.dumps(board_payload(board), indent=2, sort_keys=True) + "\n",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump the frontend parity fixtures.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed fixtures match recomputed output",
    )
    parser.add_argument(
        "--fixtures-dir",
        type=Path,
        default=FIXTURES_DIR,
        help="directory holding the committed fixture files",
    )
    args = parser.parse_args(argv)
    fixtures = render_fixtures()

    if args.check:
        missing: list[Path] = []
        out_of_date: list[Path] = []
        for name, content in sorted(fixtures.items()):
            path = args.fixtures_dir / name
            if not path.exists():
                missing.append(path)
            elif path.read_text() != content:
                out_of_date.append(path)
        for path in missing:
            print(f"missing: {path}")
        for path in out_of_date:
            print(f"out of date: {path}")
        if missing or out_of_date:
            return 1
        print(f"{len(fixtures)} fixtures up to date")
        return 0

    args.fixtures_dir.mkdir(parents=True, exist_ok=True)
    for name, content in sorted(fixtures.items()):
        path = args.fixtures_dir / name
        path.write_text(content)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
