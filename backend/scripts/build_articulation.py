"""Build `data/articulation.db` and the committed build report from ASSIST.

Four stages, cumulative: `fetch` walks the corridor and warms the on-disk
cache, `normalize` turns the cached payloads into contracts, `store` writes the
artifact, and `all` (the default) does the lot.

Network access is opt-in twice over: the fetcher defaults to offline, and only
`--stage fetch` or `--stage all` under `--allow-network` may pass that default.
Every other invocation is a pure function of the cache on disk, which is what
makes `make build-data` and the test suite safe to run at any time.

`--check` is the LOCAL committed-artifact gate (overview doc): it rebuilds from
the same cache into a temp directory and compares canonical dumps, because the
raw ASSIST cache is far too large to commit and CI therefore cannot regenerate
the corridor. CI enforces determinism through the fixture-driven store tests
instead.

Fault isolation is the build's whole posture. A failing agreement is excluded
and reported; nothing here can turn one bad payload into a failed build.
"""

import argparse
import gzip
import shutil
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, get_args

from starmap.assist.corridor import (
    ROOT_URL,
    AgreementRef,
    CorridorScope,
    PairScope,
    academic_years_url,
    agreement_url,
    institutions_url,
    walk_corridor,
)
from starmap.assist.errors import AssistFetchError, AssistNormalizeError
from starmap.assist.fetch import AssistFetcher
from starmap.assist.http import build_transport
from starmap.assist.normalize import (
    AcademicYear,
    Exclusion,
    NormalizedAgreement,
    dedupe_course_rows,
    normalize_academic_years,
    normalize_agreement,
    normalize_institutions,
)
from starmap.assist.report import BuildReport, PairReport, build_report, pair_report, write_report
from starmap.assist.store import ArticulationStore
from starmap.common.clock import SystemClock
from starmap.common.dbdump import canonical_dump
from starmap.common.sqlite import SqliteDatabase
from starmap.contracts.cc_course import CcCourse
from starmap.contracts.institution import Institution
from starmap.contracts.reason_codes import AssistBuildCode
from starmap.contracts.target_course import TargetCourse

Stage = Literal["fetch", "normalize", "store", "all"]
STAGES: tuple[str, ...] = get_args(Stage)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = REPO_ROOT / "data" / "raw" / "assist"
DEFAULT_DB_PATH = REPO_ROOT / "data" / "articulation.db"
DEFAULT_REPORT_PATH = REPO_ROOT / "data" / "reports" / "assist_build_report.json"

# SQLite's WAL sidecars belong to the file they sit beside; a rebuild that left
# them behind would resurrect rows the new build never wrote.
SQLITE_SIDECAR_SUFFIXES = ("-wal", "-shm")

# Maximum compression: this runs once per build and the result is what the
# repository carries forever, so the trade is entirely on the size side.
GZIP_LEVEL = 9


@dataclass(frozen=True, slots=True)
class BuildOutcome:
    """What one normalize pass over a walked corridor produced."""

    report: BuildReport
    institutions: tuple[Institution, ...]
    agreements: tuple[NormalizedAgreement, ...]


def open_fetcher(cache_dir: Path, *, offline: bool) -> AssistFetcher:
    return AssistFetcher(
        build_transport(),
        cache_dir,
        SystemClock(),
        root_url=ROOT_URL,
        offline=offline,
    )


def normalize_pair(
    fetcher: AssistFetcher, pair: PairScope
) -> tuple[list[NormalizedAgreement], list[Exclusion]]:
    """Every agreement of one pair, with per-agreement fault isolation.

    A dead session is the one failure that is NOT isolated, matching the walk's
    rule: it is a global condition, and swallowing it per agreement would turn
    one broken session into hundreds of bogus exclusions.
    """
    stored: list[NormalizedAgreement] = []
    excluded: list[Exclusion] = []
    for ref in sorted(pair.agreements, key=lambda item: item.assist_key):
        try:
            stored.append(normalize_ref(fetcher, ref))
        except (AssistFetchError, AssistNormalizeError) as error:
            if error.assist_reason_code is AssistBuildCode.SESSION_BOOTSTRAP_FAILED:
                raise
            excluded.append(
                Exclusion(ref.assist_key, None, error.assist_reason_code, error.message)
            )
    return stored, excluded


def normalize_ref(fetcher: AssistFetcher, ref: AgreementRef) -> NormalizedAgreement:
    return normalize_agreement(
        fetcher.fetch_json(agreement_url(ref.assist_key)),
        assist_key=ref.assist_key,
        category=ref.category,
        label=ref.label,
        sending_id=ref.sending_id,
        receiving_id=ref.receiving_id,
    )


def run_normalize(fetcher: AssistFetcher, scope: CorridorScope) -> BuildOutcome:
    """Normalize the whole walked scope and fold the build report."""
    institutions, kind_unknown = normalize_institutions(fetcher.fetch_json(institutions_url()))
    agreements: list[NormalizedAgreement] = []
    pairs: dict[tuple[int, int], PairReport] = {}
    for pair in scope.pairs:
        stored, excluded = normalize_pair(fetcher, pair)
        agreements.extend(stored)
        pairs[(pair.sending_id, pair.receiving_id)] = pair_report(pair, stored, excluded)

    # One dedup over the whole build, fed in sorted `assist_key` order, so
    # "first occurrence wins" is a property of the data rather than of the
    # order agreements happened to be normalized in.
    ordered = tuple(sorted(agreements, key=lambda item: item.agreement.assist_key))
    _, cc_conflicts, _, target_conflicts = projection_rows(ordered)
    report = build_report(
        scope,
        pairs,
        institution_kind_unknown=kind_unknown,
        course_projection_conflicts=cc_conflicts + target_conflicts,
    )
    return BuildOutcome(report=report, institutions=tuple(institutions), agreements=ordered)


def projection_rows(
    agreements: Sequence[NormalizedAgreement],
) -> tuple[list[CcCourse], int, list[TargetCourse], int]:
    """Both deduped projections and both conflict counts, from one pass."""
    cc_courses, cc_conflicts = dedupe_course_rows(
        [course for item in agreements for course in item.cc_courses]
    )
    targets, target_conflicts = dedupe_course_rows(
        [course for item in agreements for course in item.target_courses]
    )
    return cc_courses, cc_conflicts, targets, target_conflicts


def write_database(
    path: Path,
    *,
    institutions: Sequence[Institution],
    years: Sequence[AcademicYear],
    agreements: Sequence[NormalizedAgreement],
) -> None:
    """Write the artifact from scratch; a rebuild never merges into an old file."""
    reset_database_file(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    cc_courses, _, target_courses, _ = projection_rows(agreements)
    db = SqliteDatabase(path)
    try:
        store = ArticulationStore(db)
        store.put_institutions(institutions)
        store.put_academic_years(years)
        store.put_agreements(agreements)
        store.put_cc_courses(cc_courses)
        store.put_target_courses(target_courses)
        store.vacuum()
    finally:
        db.close()


def reset_database_file(path: Path) -> None:
    path.unlink(missing_ok=True)
    for suffix in SQLITE_SIDECAR_SUFFIXES:
        path.with_name(path.name + suffix).unlink(missing_ok=True)


def run_build(
    *,
    stage: Stage,
    cache_dir: Path,
    db_path: Path,
    report_path: Path,
    only_pair: tuple[int, int] | None = None,
    allow_network: bool = False,
    pack: bool = True,
) -> int:
    """One build. Returns a process exit code.

    `pack` writes the committed gzip beside the database. `--check` turns it
    off: its rebuild lands in a temp directory that is deleted moments later,
    and artifact identity is compared over canonical dumps rather than over
    compressed bytes, so gzipping a throwaway build buys nothing.
    """
    # Network is reachable from the fetch stages only; normalize and store are
    # pure functions of the cache by construction, not by discipline.
    offline = not (allow_network and stage in {"fetch", "all"})
    fetcher = open_fetcher(cache_dir, offline=offline)
    scope = walk_corridor(fetcher, only_pair=only_pair)
    if stage == "fetch":
        fetched = sum(len(pair.agreements) for pair in scope.pairs)
        print(f"fetch: {len(scope.pairs)} pairs, {fetched} agreement payloads in cache")
        return 0

    outcome = run_normalize(fetcher, scope)
    write_report(report_path, outcome.report)
    print(f"wrote {report_path}")

    if stage in {"store", "all"}:
        years = normalize_academic_years(fetcher.fetch_json(academic_years_url()))
        write_database(
            db_path, institutions=outcome.institutions, years=years, agreements=outcome.agreements
        )
        print(f"wrote {db_path}")
        if pack:
            packed = pack_database(db_path)
            print(f"wrote {packed} ({packed.stat().st_size / 1_048_576:.1f} MB)")
    print_summary(outcome.report)
    return 0


def pack_database(db_path: Path) -> Path:
    """Write the committed `<db>.gz` beside the built database.

    GitHub hard-rejects any file over 100 MB, and the fifteen-campus artifact
    is well past that, so the COMMITTED form of the artifact is the gzip and
    `articulation.db` itself is a gitignored build output (`make unpack-data`
    regenerates it from the gzip on a fresh clone).

    `mtime=0` keeps the output a pure function of the input for one zlib build.
    Artifact identity is still defined over the canonical logical dump, never
    over these bytes, exactly as the axiom already requires for SQLite files:
    the compressed bytes may legitimately differ across zlib versions, and
    `--check` compares dumps rather than files.
    """
    packed = db_path.with_suffix(db_path.suffix + ".gz")
    with (
        db_path.open("rb") as raw,
        gzip.GzipFile(packed, "wb", compresslevel=GZIP_LEVEL, mtime=0) as out,
    ):
        shutil.copyfileobj(raw, out)
    return packed


def unpack_database(db_path: Path) -> Path:
    """Restore `articulation.db` from its committed gzip (`make unpack-data`)."""
    packed = db_path.with_suffix(db_path.suffix + ".gz")
    if not packed.exists():
        raise FileNotFoundError(f"no packed artifact at {packed}")
    for suffix in SQLITE_SIDECAR_SUFFIXES:
        db_path.with_name(db_path.name + suffix).unlink(missing_ok=True)
    with gzip.open(packed, "rb") as raw, db_path.open("wb") as out:
        shutil.copyfileobj(raw, out)
    return db_path


def print_summary(report: BuildReport) -> None:
    totals = report.pairs
    print(
        f"pairs: {len(totals)}  "
        f"agreements stored: {sum(pair.agreements_stored for pair in totals)}  "
        f"excluded: {sum(len(pair.agreements_excluded) for pair in totals)}  "
        f"articulations stored: {sum(pair.articulations_stored for pair in totals)}  "
        f"excluded: {sum(len(pair.articulations_excluded) for pair in totals)}"
    )


def run_check(
    *,
    cache_dir: Path,
    db_path: Path,
    report_path: Path,
    only_pair: tuple[int, int] | None = None,
) -> int:
    """Rebuild from the same cache into a temp directory and compare artifacts."""
    missing = [path for path in (db_path, report_path) if not path.exists()]
    for path in missing:
        print(f"missing: {path}")
    if missing:
        return 1

    with tempfile.TemporaryDirectory() as directory:
        scratch = Path(directory)
        candidate_db = scratch / db_path.name
        candidate_report = scratch / report_path.name
        exit_code = run_build(
            stage="store",
            cache_dir=cache_dir,
            db_path=candidate_db,
            report_path=candidate_report,
            only_pair=only_pair,
            pack=False,
        )
        if exit_code != 0:
            return exit_code
        drifted = [
            path
            for path, committed, rebuilt in (
                (db_path, canonical_dump(db_path), canonical_dump(candidate_db)),
                (
                    report_path,
                    report_path.read_text(encoding="utf-8"),
                    candidate_report.read_text(encoding="utf-8"),
                ),
            )
            if committed != rebuilt
        ]
    for path in drifted:
        print(f"out of date: {path}")
    if drifted:
        return 1
    print("articulation artifacts regenerate identically")
    return 0


def parse_pair(value: str) -> tuple[int, int]:
    sending, _, receiving = value.partition(":")
    if not sending.isdigit() or not receiving.isdigit():
        raise argparse.ArgumentTypeError(
            f"expected SENDING:RECEIVING institution ids, got {value!r}"
        )
    return int(sending), int(receiving)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the ASSIST articulation artifact.")
    parser.add_argument("--stage", choices=STAGES, default="all", help="which stages to run")
    parser.add_argument(
        "--allow-network",
        action="store_true",
        help="permit live ASSIST requests during the fetch stage (otherwise cache-only)",
    )
    parser.add_argument(
        "--pair", type=parse_pair, default=None, help="restrict to one pair, e.g. 113:7"
    )
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH, help="artifact path")
    parser.add_argument(
        "--check",
        action="store_true",
        help="rebuild from cache and verify the committed artifacts are identical",
    )
    parser.add_argument(
        "--unpack",
        action="store_true",
        help="restore the database from its committed gzip; no cache needed",
    )
    args = parser.parse_args(argv)
    stage: Stage = args.stage

    if args.unpack:
        restored = unpack_database(args.db)
        print(f"wrote {restored} ({restored.stat().st_size / 1_048_576:.1f} MB)")
        return 0

    if args.check:
        return run_check(
            cache_dir=DEFAULT_CACHE_DIR,
            db_path=args.db,
            report_path=DEFAULT_REPORT_PATH,
            only_pair=args.pair,
        )
    try:
        return run_build(
            stage=stage,
            cache_dir=DEFAULT_CACHE_DIR,
            db_path=args.db,
            report_path=DEFAULT_REPORT_PATH,
            only_pair=args.pair,
            allow_network=args.allow_network,
        )
    except AssistFetchError as error:
        # The one non-isolated failure: a dead session, or an offline run whose
        # cache does not hold what the walk needs.
        print(f"{error.assist_reason_code.value}: {error.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
