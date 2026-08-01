# Increment 5: ASSIST Fetch, Normalize, Store

Goal: the fully deterministic articulation build pipeline: a session-bootstrapping polite fetcher over the corridor scope, two-stage normalization into the increment 4 contracts, the `articulation.db` store, and the build report.
Binding mechanism references: the spike doc (endpoints, the XSRF mechanics, the double-decode model, the implications list), TR 4.3 (SQLite kernel), and the fault-isolation axioms in `CLAUDE.md`.
No LLM anywhere in this increment (axiom); no network in any test.

The full corridor fetch is a NETWORK permission gate: the executor must get an explicit user go-ahead before the first live request (overview doc, "Permission gates").
Everything else in this increment runs offline against the captured fixtures.

## Package moves

Create `backend/src/starmap/assist/` with modules `__init__.py`, `errors.py`, `http.py`, `fetch.py`, `corridor.py`, `normalize.py`, `store.py`, `report.py`.
Delete the empty pre-pivot `backend/src/starmap/catalog/` package (plan architecture section: "renamed/absorbed into `assist/`").
`assist/` imports only `common/` and `contracts/` (region-boundary axiom).

## `assist/errors.py`

- `AssistError(StarmapError)` base.
- `AssistFetchError(AssistError)`: network and session failures; `reason_code` from `AssistBuildCode` (`session_bootstrap_failed` or `agreement_fetch_failed`).
- `AssistNormalizeError(AssistError)`: per-agreement normalization failures; `reason_code` from `AssistBuildCode`; always caught by the per-agreement isolation loop and recorded as an exclusion, never propagated out of the normalize stage.

## `assist/http.py`: the transport seam

The fetch layer is faked at the network boundary only (testing strategy, "Hard Rules").

- `HttpResponse` frozen dataclass: `status: int`, `body: bytes`.
- `HttpTransport` Protocol: `get(url: str, headers: dict[str, str]) -> HttpResponse`; raising `OSError`/`urllib.error.URLError` signals network failure.
- `UrllibTransport`: production implementation over `urllib.request` with a shared `http.cookiejar.CookieJar` via `HTTPCookieProcessor` (the jar is what persists the ASSIST session cookies across calls); `cookie_value(name) -> str | None` exposes the non-HttpOnly `X-XSRF-TOKEN` cookie value for header echo; 30 s per-request timeout; no retries at this layer.
- `FakeHttpTransport` test twin in `backend/tests/support/http.py`: a scripted `dict[url, HttpResponse | Exception]` plus a recorded request list, in the FakeTransport style of TR 4.6.

Locked User-Agent, sent on every request (the spike confirmed a browser UA is required):
`Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36`.

## `assist/fetch.py`: session, cache, endpoints

`AssistFetcher(transport, cache_dir: Path, clock: Clock, sleeper: Callable[[float], None])`.

Session bootstrap (the spike doc's "Access mechanics" verbatim):

1. `GET https://www.assist.org/` through the transport (fills the cookie jar).
2. Read the `X-XSRF-TOKEN` cookie value; absence raises `AssistFetchError(session_bootstrap_failed)`.
3. Every subsequent API request sends headers: the UA above, `Accept: application/json`, and `X-XSRF-TOKEN: <cookie value>`.
4. If an API response has HTTP status 400, re-bootstrap ONCE and retry the request once; a second 400 raises `AssistFetchError(agreement_fetch_failed)` naming the URL.

Politeness, locked: at least 1.0 s between consecutive NETWORK requests, enforced with `clock.monotonic()` plus the injected sleeper; cache hits neither sleep nor touch the network.

On-disk cache, locked:

- Path: `data/raw/assist/<sha256_hex(url)[:16]>.json`, raw response body bytes verbatim.
- Manifest: `data/raw/assist/manifest.jsonl`, one line per NETWORK fetch: `{"url": ..., "key": ..., "status": ..., "fetched_at": <ISO from clock.now()>}`; append-only; gitignored along with the whole cache (overview doc, "Committed-artifact identity").
- `fetch_json(url) -> object`: cache hit reads and `json.loads` the file; miss goes to the network (session-bootstrapping lazily on first need), writes the cache file, appends the manifest line.
- `offline` mode flag: a cache miss raises `AssistFetchError(agreement_fetch_failed)` instead of touching the network; this is how tests and `make build-data` run.

Endpoint URL builders (paths verified in the spike doc, "Endpoints"):

- `academic_years_url()` -> `https://www.assist.org/api/AcademicYears`
- `institutions_url()` -> `https://www.assist.org/api/institutions`
- `categories_url(receiving_id, sending_id, year_id)` -> `/api/agreements/categories?receivingInstitutionId=&sendingInstitutionId=&academicYearId=`
- `agreements_url(receiving_id, sending_id, year_id, category_code)` -> `/api/agreements?...&categoryCode=` with `category_code` in `major | dept`
- `agreement_url(key)` -> `/api/articulation/Agreements?Key=<urllib.parse.quote(key, safe="")>`

## `assist/corridor.py`: the corridor scope (locked constants)

```python
BASE_URL = "https://www.assist.org"
TARGET_IDS = (7, 39, 117, 120)          # UCSD, SJSU, UCLA, UCI (plan corridor, ids from institutions.json)
DEMO_SENDING_ID = 113                    # De Anza
DEMO_RECEIVING_ID = 7                    # UCSD
PINNED_MAJOR_KEYWORDS = ("computer science", "economics", "psychology", "biology", "business")
PREFERRED_YEAR_ID = 76                   # 2025-2026, latest published (spike doc)
YEAR_FALLBACK_DEPTH = 2                  # try 76, then 75, then 74 per pair
```

Corridor walk (the fetch stage), locked order and selection rules:

1. Fetch academic years and institutions.
2. Sending side = every institution with `isCommunityCollege: true`, sorted by id (116 per the fixture; the authoritative filter per spike implication 5).
3. For each pair `(cc, target)` in (cc id asc, target id asc) order: fetch categories at `PREFERRED_YEAR_ID`; if the `major` category has `hasReports: false`, step the year id down by one, at most `YEAR_FALLBACK_DEPTH` times; record the year used per pair (spike implication 6); if no year in range has reports, record the pair as empty in the build report and continue.
4. Fetch the major reports list at the chosen year; select reports whose `label` casefold-contains any `PINNED_MAJOR_KEYWORDS` entry; for the demo pair select ALL major reports; fetch each selected agreement payload by `key`.
5. Demo pair only: also fetch the dept reports list and every dept agreement payload (dept depth beyond the demo pair is cuttable major-depth per the plan; the sending-CC breadth is never cut).

Volume sanity per the plan: roughly 2,300-2,600 requests, about 40-45 minutes at 1 req/s, one-time (cached thereafter).

## `assist/normalize.py`: two-stage decode into contracts

Stage A, envelope (spike doc, "Agreement payload model"):

- `decode_envelope(raw: object) -> dict`: require `isSuccessful` true and `result` a dict, else `AssistNormalizeError(envelope_invalid)`.
- `decode_field(result: dict, name: str) -> object`: `json.loads` of the stringified field, `AssistNormalizeError(field_decode_failed)` naming the field on any failure; applied to `receivingInstitution`, `sendingInstitution`, `academicYear`, `templateAssets` (may be null: dept agreements), `articulations`.

Stage B, mapping:

`normalize_institution(raw) -> Institution | None`, from an `institutions.json` entry:

- `code`: strip whitespace padding.
- `name`: the `names[]` entry with the highest `fromYear` (absent `fromYear` reads as 0).
- `kind`: `isCommunityCollege` true -> `cc`; else `category` 1 -> `uc`; else `category` 0 -> `csu`; anything else (observed: category 5, private institutions) returns None and is counted in the build report under `institution_kind_unknown`, never stored, never fatal.

`normalize_agreement(raw, *, assist_key, category, label, sending_id, receiving_id) -> NormalizedAgreement`, where `NormalizedAgreement` is a frozen container of `agreement: Agreement`, `articulations: list[Articulation]`, `requirement_groups: list[RequirementGroupAsset]`, `cc_courses: list[CcCourse]`, `target_courses: list[TargetCourse]`, `exclusions: list[Exclusion]` (`Exclusion` = frozen `(assist_key, position | None, reason_code, detail)`).

Articulation list dispatch (spike implication 3): a decoded `articulations` entry with a `templateCellId` key is the template-cell wrapper (inner articulation under `articulation`, cell id captured); otherwise it is a bare base-model articulation (dept).
`position` = the entry's index in the decoded array.

Per-articulation mapping, inside the per-articulation try/except (fault isolation; an exclusion removes one articulation, not the agreement):

1. Inner `type` must be `"Course"`; anything else (e.g. `Series`, requirement types) -> exclusion `articulation_type_unsupported` (spike doc: tolerate unknown types by exclusion, not crash).
2. Receiving `course` maps to `ReceivingCourse` via `course_code_from_parts(prefix, courseNumber)`; normalization failure -> exclusion `course_code_unparseable`.
3. `sendingArticulation` null OR `items` empty -> `sending_expr = None`, carry `noArticulationReason` through (both encodings mean "No Course Articulated"; overview doc payload facts).
4. Otherwise build the expression tree, locked algorithm:
   - Sort groups by `position`.
   - Per group: leaves are `CourseLeaf(course=course_code_from_parts(...))` for the group's `items` sorted by `position`; a non-`Course` item type -> exclusion `articulation_type_unsupported`.
   - Group node: a single leaf stands alone; two-plus leaves wrap in `AllOf` when `courseConjunction == "And"`, `AnyOf` when `"Or"`.
   - Group-level and course-level `attributes` map through `advisement_texts` (below); each returned text becomes a `NoteLeaf` appended INSIDE the group node (a bare leaf plus notes wraps into `AllOf([leaf, *notes])`).
   - One group: the expression is that group node.
   - Multiple groups: collect `courseGroupConjunctions[*].groupConjunction`; all `"Or"` -> `AnyOf(group nodes)`; all `"And"` -> `AllOf(group nodes)`; mixed values -> exclusion `mixed_group_conjunction` (only `Or` observed; spike doc).
   - Maximum resulting depth is 3 (outer group joiner > group node > leaf), within `MAX_DEPTH`.
5. Articulation-level and sending-articulation-level `attributes` map through `advisement_texts` into `Articulation.advisements`.
6. Every `CourseLeaf` course on the sending side also emits a `CcCourse` row (institution = sending id; title/units from the raw course item); the receiving course and every template cell course emit `TargetCourse` rows.

`advisement_texts(attributes: list[object]) -> list[str]`, the fixture-pending gate (overview doc, "Advisements are fixture-pending"): empty list -> `[]`; ANY non-empty list -> `AssistNormalizeError(advisement_shape_unknown)`, which the isolation loop records as that articulation's exclusion.
Split S9c replaces the raise with the real mapping once an advisement-bearing payload is captured as a fixture; do not guess the shape before then.

Template assets (major agreements only; `templateAssets` null for dept):

- Keep only entries with `type == "RequirementGroup"`, sorted by `position`; `GeneralTitle`/`GeneralText` entries are dropped for v1 (prose, not requirements; recorded as a future enrichment, not built now).
- Per group: `instruction` null -> `conjunction = "And"`; `instruction.type == "Conjunction"` -> its `conjunction` value; any other instruction shape -> exclusion `template_shape_unsupported` for that group (the agreement still stores).
- Sections sorted by `position`; each section's rows sorted by `position`; every row must contain exactly one cell of `type == "Course"` (the only observed shape); anything else -> exclusion `template_shape_unsupported` for the group.
- Cell -> `TemplateCell(cell_id=cell["id"], course=ReceivingCourse(...))`; group/section `advisements` lists go through `advisement_texts`.

Projection dedup, locked: `cc_courses` and `target_courses` dedupe by `(institution_id, course_code)` across ALL agreements, processed in sorted `assist_key` order, first occurrence wins; a later occurrence with a different title or units is counted in the build report under `course_projection_conflict` (kept-first policy), never stored twice.

## `assist/store.py`: `articulation.db`

`ensure_schema(db, component="articulation", version=1, statements=...)` with exactly these tables (payload columns hold canonical contract JSON, reads re-validate through `model_validate_json`; TR 1.1 responsibility split):

```sql
CREATE TABLE IF NOT EXISTS institutions (
    assist_id INTEGER PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS academic_years (
    year_id INTEGER PRIMARY KEY, label TEXT NOT NULL, fall_year INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS agreements (
    agreement_id TEXT PRIMARY KEY, assist_key TEXT NOT NULL UNIQUE,
    sending_institution_id INTEGER NOT NULL, receiving_institution_id INTEGER NOT NULL,
    academic_year_id INTEGER NOT NULL, category TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS articulations (
    agreement_id TEXT NOT NULL, position INTEGER NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (agreement_id, position));
CREATE TABLE IF NOT EXISTS agreement_requirements (
    agreement_id TEXT NOT NULL, position INTEGER NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (agreement_id, position));
CREATE TABLE IF NOT EXISTS cc_courses (
    institution_id INTEGER NOT NULL, course_code TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (institution_id, course_code));
CREATE TABLE IF NOT EXISTS target_courses (
    institution_id INTEGER NOT NULL, course_code TEXT NOT NULL, payload TEXT NOT NULL,
    PRIMARY KEY (institution_id, course_code));
```

Locked store discipline: inserts in deterministic order (institutions by `assist_id`, years by `year_id`, agreements by `assist_key`, articulations and requirements by `(agreement_id, position)`, both course projections by `(institution_id, course_code)`); no timestamps anywhere in the artifact; `VACUUM` before finalizing; the latest year per pair is DERIVED at read time as `MAX(academic_year_id)` over that pair's agreements (no extra table).
Read surface (consumed by increments 6-7): `load_institutions()`, `load_agreements_for_pair(sending_id, receiving_id)`, `load_articulations(agreement_id)`, `load_requirements(agreement_id)`, `load_cc_courses(institution_id)`, `load_target_courses(institution_id)`; every read re-validates payloads through the contracts.

## `assist/report.py`: the build report

`data/reports/assist_build_report.json`, committed, deterministic: `json.dumps(report, indent=2, sort_keys=True) + "\n"`, NO timestamps (fetch dates live in the gitignored manifest).
Shape, locked:

```json
{
  "corridor": {"targets": [...], "sending_count": 116, "preferred_year_id": 76},
  "pairs": [
    {"sending_id": 113, "receiving_id": 7, "year_id": 76,
     "major_reports": 168, "major_selected": 168, "dept_reports": 86,
     "agreements_stored": 0, "agreements_excluded": [{"assist_key": "...", "reason_code": "...", "detail": "..."}],
     "articulations_stored": 0,
     "articulations_excluded": [{"assist_key": "...", "position": 0, "reason_code": "...", "detail": "..."}]}
  ],
  "totals": {"agreements_stored": 0, "agreements_excluded": 0, "articulations_excluded": 0,
             "institution_kind_unknown": 0, "course_projection_conflicts": 0,
             "advisement_shape_unknown": 0}
}
```

Every exclusion carries its typed `AssistBuildCode`; no silent drops (axiom).
The `advisement_shape_unknown` total is the S9c trigger (overview doc).

## `backend/scripts/build_articulation.py`

CLI, locked flags: `--stage fetch|normalize|store|all` (default `all`), `--allow-network` (without it every stage is offline and a cache miss fails typed), `--pair S:R` (restrict to one pair, e.g. `113:7`), `--db PATH` (default `data/articulation.db`), `--check`.

- `fetch` walks the corridor through the cache (network only under `--allow-network`, which the executor only uses after the user's go-ahead).
- `normalize` + `store` run from cache only and write the db and the build report.
- `--check` regenerates the db from cache into a temp directory and compares `canonical_dump` outputs against the committed file, exiting non-zero on drift; this is the LOCAL gate (overview doc, "Committed-artifact identity"): it requires the local cache and is NOT wired into CI.

Makefile changes: `build-data` becomes `cd backend && uv run python scripts/build_articulation.py --stage all` (offline, cache-driven); add `build-check` running `--check`; `check` itself is unchanged (lint, typecheck, test, schema-check).
The stale `scripts/build_catalog.py` reference in the current Makefile disappears with this edit.

## Tests (all offline; fixtures are the only payload source)

- Fetcher against `FakeHttpTransport`: bootstrap sends the cookie header echo on API calls; missing cookie -> typed `session_bootstrap_failed`; 400 triggers exactly one re-bootstrap plus retry, second 400 -> typed failure naming the URL; 1 req/s pacing via recorded sleeper (`sleeps` between two network calls >= 1.0); cache hit performs zero transport calls and zero sleeps; offline mode raises typed on miss; manifest line written per network fetch.
- Normalize on the two captured agreement fixtures end-to-end: the major fixture yields 8 articulations (MATH 20D `any`-of-two-singles, MATH 20E `all`-of-two, positions stable) and 4 requirement groups including the `Or` group with cells CSE 15L / CSE 29; the dept fixture yields 11 articulations with MATH 10B/10C as `sending_expr` null; every produced object passes its contract.
- Normalize fault isolation: a poisoned copy of a fixture (mutated in-test, never on disk) with an unknown articulation `type`, an unparseable course code, and a non-empty `attributes` list produces exactly three typed exclusions and keeps the remaining articulations (the "one poisoned member never breaks the build" seam per the testing strategy).
- Envelope failures: `isSuccessful` false -> `envelope_invalid`; corrupt stringified field -> `field_decode_failed` naming the field.
- Institution normalization: De Anza -> `cc`, UCSD -> `uc`, CSUMA -> `csu` with the 2015 name selected, a category 5 entry -> None counted.
- Store determinism: normalize + store the two fixtures twice into two temp dbs, assert equal `canonical_dump` outputs; re-open and re-validate payload round trips.
- Report: built from the fixture pair, byte-stable across two runs, exclusion entries carry typed codes.
- Build script: `--stage all` offline over a temp cache seeded from the fixtures produces db + report; `--check` passes on itself and fails after a row mutation.

## Split S9c: the live corridor fetch (NETWORK gate)

Run only after the user's explicit go-ahead in that session:

1. `build_articulation.py --stage fetch --allow-network` for the full corridor (resumable: the cache makes reruns cheap).
2. `--stage normalize` + `store`; review the build report; expect a non-zero `advisement_shape_unknown` count.
3. Pick one excluded advisement-bearing agreement; copy its cached payload into `backend/tests/fixtures/assist/` as `agreement_with_advisements_<sending>_to_<receiving>_y<year>.json`; pin the real `attributes` shape in `advisement_texts` with tests; remove the all-attributes-empty assertion from `test_assist_fixture_alignment.py` (doc 01) and extend it to cover the new fixture.
4. Rebuild; confirm the exclusion count drops; spot-check the demo pair against assist.org by hand (agreement counts, the De Anza CIS to UCSD CSE mappings per the plan's verification section) and record the checks in `docs/notes/articulation_spotchecks.md`.
5. Run `make build-check`; commit `articulation.db` + report + fixture + spot-check note after confirming artifact size with the user.

## Exit criteria

- `make check` green offline; the full test list above passing.
- `articulation.db` built from cache for the corridor scope; build report reviewed; spot-check note written (S9c).
- `make build-check` proves canonical-dump identity locally.
- The advisement mapping is pinned by a real captured fixture, not a guess.
