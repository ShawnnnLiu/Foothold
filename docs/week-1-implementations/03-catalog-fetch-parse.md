# Increment 3: Catalog Fetch and Parse, All Departments

Goal: `catalog.db` populated from cached HTML for every fetched department, with a reviewed parse report and per-dept fault isolation.
Consumes the increment 1 findings doc (`docs/notes/day1_spikes.md`); where this doc says "per spike", the recorded finding is binding.
Network gate: the full ~80-page fetch needs user go-ahead; everything else runs offline on `data/raw/`.

## `catalog/fetch.py`

`BulletinFetcher(cache_dir: Path, clock: Clock, sleeper: Callable[[float], None], *, user_agent: str, timeout_seconds: float = 20.0)`.

- `fetch(url: str) -> FetchResult` where `FetchResult` is a frozen dataclass `(url, text, sha256, date_fetched, from_cache)`.
- Cache format exactly as locked in doc 01: `data/raw/<sha256(url)>.html` plus an appended `manifest.jsonl` line on every network fetch.
  Cache hit: read file, look up the newest manifest line for the url for `date_fetched`, no sleep, no network.
- Politeness: before every NETWORK request, sleep so that at least 1.0 s has passed since the previous network request (tracked via `clock.monotonic()`); the sleeper is injected so tests never sleep.
- robots.txt: fetched once per host via stdlib `RobotFileParser`, cached for the fetcher's lifetime; unreachable robots reads as allow; a disallowed URL raises `FetchDisallowedError`.
- Only `http`/`https` URLs with a netloc; anything else raises without opening.
- Response decoded with declared charset else UTF-8-with-replacement; non-2xx raises `FetchFailedError(StarmapError, reason_code=BuildCode.dept_fetch_failed)` carrying url and status.
- No retries; a failed dept is isolation's problem, not the fetcher's.

`discover_departments(index_html: str) -> list[Department]` parses the departments-instruction index into frozen `(department_code, name, url)` records, sorted by code; the link-selection rule comes from the spike findings.

## `catalog/parse_bulletin.py`

Pure functions over HTML strings; BeautifulSoup with the stdlib `html.parser` backend (no lxml dependency).
Output intermediate frozen dataclasses (NOT contracts; contract validation happens in the store): `ParsedCourse(course_code, title, points_min, points_max, description, prereq_prose, linked_codes: tuple[str, ...], bulletin_url)`, `ParsedOffering(course_code, term, year, instructors: tuple[str, ...])`, `ParsedRequirementTable(name, rows)`.

`parse_department(html: str, *, dept_code: str, page_url: str) -> DeptParseResult` with fields `(courses, offerings, requirement_tables, warnings: tuple[str, ...])`.

Locked parsing rules, adjusted only where the spike recorded different reality:

- Course blocks: `select(".courseblock")`; title from `.courseblocktitle` text after whitespace normalization.
  Title regex: `^(?P<code>[A-Z]{2,4}\s+[A-Z]{0,2}[0-9]{4})\s+(?P<title>.+?)\.?\s+(?P<pts>\d+(?:\.\d+)?(?:-\d+(?:\.\d+)?)?)\s*points?\.?$` case-insensitive on the points suffix; a non-matching title emits a warning and skips the block (never raises).
- Points: `a-b` range fills min/max; single value fills both.
- Description: `.courseblockdesc` text; prereq prose is the substring from the first occurrence of a prereq marker (`Prerequisites:` or `Prerequisite:` or `Corequisites:` per spike) to the end of its sentence block; keep the full description intact as well.
- Linked codes: every `a[href*="/search/?P="]` within the block; decode the `P` query value, `normalize_course_code`, dedupe preserving first occurrence; codes failing normalization emit warnings, never crash.
- Offerings: term subheading pattern from the spike (`^(Fall|Spring|Summer) (\d{4})`); instructors split per the spike-recorded delimiter; term lowercased into the contract enum.
- Requirement tables: every `.sc_courselist`; per-row extraction of code cell and comment/heading rows per the spike-recorded column classes; area-header rows start a new named table.
  This is best-effort: rows that fit no rule become warnings.

## `catalog/store.py`

`CatalogStore(db: SqliteDatabase)` with `ensure_schema(component="catalog", version=1, statements=DDL)`.

DDL (locked):

```sql
CREATE TABLE IF NOT EXISTS departments (
    department_code TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS majors (
    major_id TEXT PRIMARY KEY, department_code TEXT NOT NULL,
    name TEXT NOT NULL, curated INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS courses (
    course_code TEXT PRIMARY KEY, department_code TEXT NOT NULL,
    title TEXT NOT NULL, points_min REAL NOT NULL, points_max REAL NOT NULL,
    description TEXT, prereq_prose TEXT, linked_codes_json TEXT NOT NULL,
    prereq_expr_json TEXT, prereq_confidence TEXT NOT NULL DEFAULT 'none',
    bulletin_url TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS offerings (
    course_code TEXT NOT NULL, term TEXT NOT NULL, year INTEGER NOT NULL,
    instructors_json TEXT NOT NULL,
    PRIMARY KEY (course_code, term, year));
CREATE TABLE IF NOT EXISTS requirement_groups (
    requirement_group_id TEXT PRIMARY KEY, major_id TEXT NOT NULL,
    name TEXT NOT NULL, payload TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_courses_dept ON courses(department_code);
```

Write path: all rows built by dumping validated contract models (`payload` = canonical model JSON for requirement groups; courses assembled from `Course` contract instances); reads rebuild through `model_validate`, never trusted.
Insert order: departments, then courses sorted by code, then offerings sorted by `(course_code, year, term)`, then requirement groups sorted by id, inside one transaction per dept; determinism plus `VACUUM` on finalize keeps the canonical dump stable.
`linked_codes_json` is stored even though it is not a `Course` contract field: it is build-internal state consumed by stage 3 (extraction vocabulary); keep the `Course` contract free of it and assemble contract instances without it on read.

## `backend/scripts/build_catalog.py` (stages 1-2)

CLI: `--stage fetch|parse|all` (default `all` runs the stages that exist so far), `--allow-network` (without it, fetch serves cache-only and a cache miss is a dept failure), `--depts CODE,CODE` (subset for iteration), `--db data/catalog.db`, `--check`.

- Stage `fetch`: discover departments, fetch each dept page (1 req/s on misses), record per-dept status.
- Stage `parse`: for each cached dept, `try/except` around `parse_department`; a raising dept gets status `dept_parse_failed` and lands on the exclusion list; the build continues (axiom: a failing department never breaks the build).
- Parse report: `data/reports/parse_report.json`, committed, deterministic (no timestamps, keys sorted, depts sorted by code).
  Shape: `{"departments": {"<code>": {"status": "ok" | "excluded", "reason_code": null | str, "courses": n, "offerings": n, "requirement_tables": n, "warnings": [...sorted]}}, "totals": {...}, "excluded": [...codes]}`.
- `--check`: regenerate `catalog.db` into a temp dir from cache (stages parse onward, stage 3 served entirely from the extraction cache once increment 5 lands), compare `canonical_dump` outputs, exit non-zero on drift; wire a `make` alias later increments extend.
- Stage 3/4/5 hooks exist as named stubs that raise `NotImplementedError` mentioning their increment; the CLI help lists them.

## Tests (all offline)

- Fetcher: fake `urlopen` + `FrozenClock` + recorded sleeper; assertions: 1 req/s spacing (`sleeps` values), cache hit does not sleep or hit network, manifest line appended once per network fetch, robots consulted once per host, disallowed raises, non-http rejected, non-2xx typed failure.
- Parser: small committed HTML fixtures under `backend/tests/fixtures/html/` extracted (hand-trimmed, not whole pages) from the spike cache for CS and Econ plus synthetic edge cases: title without points, range points, prereq prose with links, malformed code link, requirement table with header rows.
  Assert exact `ParsedCourse` tuples, warning emission instead of raises.
- Store: round-trip courses/offerings/groups through the db and back through contracts; canonical dump equality across two identically-sourced builds; insert-order independence via the dump.
- Build orchestration: a dept whose HTML raises lands excluded with `dept_parse_failed`, run exits 0, report matches the locked shape byte-for-byte against a pinned fixture.

## Exit criteria

- Full fetch completed once with user go-ahead; all dept pages cached; failures recorded, not fatal.
- `catalog.db` populated for all non-excluded depts; parse report committed and reviewed (course counts sane: CS > 50, total > 2000 or the deviation explained in the report review note).
- SQL spot-checks recorded in `docs/notes/catalog_spotchecks.md`: COMS W3134, W3157, W4111 rows present with prose and linked codes; ECON UN3211 present; offerings joined for at least one CS course.
- `make check` green; `--check` mode proven on a regenerate.
