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
- `HttpTransport` Protocol: `get(url: str, headers: dict[str, str]) -> HttpResponse`, `cookie_value(name: str) -> str | None`, and `clear_cookies() -> None`; raising `OSError`/`urllib.error.URLError` signals network failure.
  `cookie_value` is on the Protocol, not only on the production class, because `fetch.py` reads the XSRF cookie through the seam; a Protocol without it cannot be satisfied by the test twin.
  `clear_cookies` is on the Protocol for the same reason: the jar IS the session, so emptying it is how `fetch.py` starts a new one (added in S9c, see the session-quota rule below).
- `UrllibTransport`: production implementation over `urllib.request` with a shared `http.cookiejar.CookieJar` via `HTTPCookieProcessor` (the jar is what persists the ASSIST session cookies across calls); `cookie_value(name) -> str | None` exposes the non-HttpOnly `X-XSRF-TOKEN` cookie value for header echo; 30 s per-request timeout; no retries at this layer.
  A `urllib.error.HTTPError` is translated back into a plain `HttpResponse` carrying its status, because ASSIST answers 400 as ordinary control flow and `urllib` raises on every 4xx/5xx; `URLError`/`OSError` propagate untouched.
- `build_transport()` production factory (the `llm/transport_anthropic.build_client` pattern): the only thing that creates a cookie jar, so tests never build a networked object implicitly.
- `FakeHttpTransport` test twin in `backend/tests/support/http.py`: a scripted `dict[url, HttpResponse | Exception | list[...]]` plus a recorded request list, in the FakeTransport style of TR 4.6.
  A list value is consumed left to right and asserts when exhausted, which is what makes the "400, then 200 after the re-bootstrap" sequence expressible; a bare value answers its url unlimited times; there is no default response, so an unscripted url is a loud test failure.

Locked User-Agent, sent on every request (the spike confirmed a browser UA is required):
`Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36`.

## `assist/fetch.py`: session and cache

`AssistFetcher(transport, cache_dir: Path, clock: Clock, sleeper: Callable[[float], None] = time.sleep, *, root_url: str, offline: bool = True)`.

`offline` DEFAULTS to true: network access is opt-in, which is what makes the S9c permission gate a deliberate act rather than an omission.
`root_url` is injected rather than imported so this module keeps no ASSIST endpoint knowledge; `corridor.ROOT_URL` is what every caller passes.

Session bootstrap (the spike doc's "Access mechanics" verbatim):

1. `GET https://www.assist.org/` through the transport (fills the cookie jar).
2. Read the `X-XSRF-TOKEN` cookie value; absence raises `AssistFetchError(session_bootstrap_failed)`.
3. Every subsequent API request sends headers: the UA above, `Accept: application/json`, and `X-XSRF-TOKEN: <cookie value>`.
4. If an API response has HTTP status 400, re-bootstrap ONCE and retry the request once; a second 400 raises `AssistFetchError(agreement_fetch_failed)` naming the URL.

Status handling, locked in full:

| Condition | Outcome |
|---|---|
| Bootstrap `GET /` non-200, or 200 with no `X-XSRF-TOKEN` cookie | `AssistFetchError(session_bootstrap_failed)` |
| API 200 | cache the body and return the decoded JSON |
| API 400 | re-bootstrap once, retry once; a second 400 is `agreement_fetch_failed` |
| API 429 | renew the session (empty the jar, re-bootstrap) and retry, at most `MAX_SESSION_RENEWALS` = 3 times; still 429 is `agreement_fetch_failed` naming the URL |
| Any other API non-200 | `agreement_fetch_failed` naming the URL and the status (never a re-bootstrap: a 500 is not a session problem) |
| Body that is not valid JSON | `agreement_fetch_failed` naming the URL |
| `OSError`/`URLError` out of the transport | `agreement_fetch_failed` naming the URL and the exception TYPE NAME, chained with `raise ... from` |

Error messages carry urls, statuses, and exception type names only.
They never carry response bodies and never carry the `X-XSRF-TOKEN` value, mirroring the same rule in `llm/errors.py`: a body can quote request content, and the token is a session credential.

Politeness, locked: at least 1.0 s between consecutive NETWORK requests, enforced with `clock.monotonic()` plus the injected sleeper; cache hits neither sleep nor touch the network.

Session quota, locked in S9c against live ASSIST (this replaces the pre-S9c assumption that one session lasts a whole run).
ASSIST meters requests PER SESSION, not per unit time: the S9c pilot measured 55 requests before every later request answered 429, a second session measured 50, and a fresh session then succeeded immediately with NO idle period while the exhausted one stayed shut.
The 429 responses carry no `Retry-After` and no rate-limit headers, so there is nothing to obey but the observation.
Therefore:

- a bootstrap starts a NEW session: `clear_cookies()` first, then `GET /`, so the renewal cannot inherit the spent quota;
- the fetcher renews PROACTIVELY every `SESSION_REQUEST_BUDGET` = 40 API requests, which is below the smaller observation, so the walk spends requests on payloads instead of on rejections (politeness axiom: fewer refused requests, not more);
- a 429 renews REACTIVELY as the status table says, bounded at 3.

Pacing is unchanged by all of this: the quota is about session identity, not about going faster.

On-disk cache, locked:

- Path: `data/raw/assist/<sha256_hex(url)[:16]>.json`, raw response body bytes verbatim.
- Manifest: `data/raw/assist/manifest.jsonl`, one line per `fetch_json` NETWORK outcome: `{"url": ..., "key": ..., "status": ..., "fetched_at": <ISO from clock.now()>}` written with `sort_keys=True`; append-only; gitignored along with the whole cache (overview doc, "Committed-artifact identity").
  A non-200 is recorded too, so a failure leaves a trace instead of vanishing (no silent drops); the bootstrap `GET /` is session plumbing rather than a fetched payload and is not recorded.
- `fetch_json(url) -> object`: cache hit reads and `json.loads` the file; miss goes to the network (session-bootstrapping lazily on first need), writes the cache file, appends the manifest line.
- `offline` mode flag: a cache miss raises `AssistFetchError(agreement_fetch_failed)` instead of touching the network; this is how tests and `make build-data` run.
- The cache directory is created on first WRITE, so an offline run against a missing directory fails typed instead of creating one.

## `assist/corridor.py`: the corridor scope (locked constants)

```python
BASE_URL = "https://www.assist.org"
ROOT_URL = f"{BASE_URL}/"               # the session-bootstrap url passed to AssistFetcher
TARGET_IDS = (7, 11, 26, 39, 42, 46, 79, 81, 89, 117, 120, 128, 129, 132, 144)
DEMO_SENDING_ID = 113                    # De Anza
DEMO_RECEIVING_ID = 7                    # UCSD
PINNED_MAJOR_KEYWORDS = ("computer science", "economics", "psychology", "biology", "business")
MAX_MAJORS_PER_PAIR: int | None = None   # uncapped (S9d; see below)
PREFERRED_YEAR_ID = 76                   # 2025-2026, latest published (spike doc)
YEAR_FALLBACK_DEPTH = 2                  # try 76, then 75, then 74 per pair
```

`TARGET_IDS` was widened from four campuses to fifteen in S9d: all nine UC undergraduate campuses (7 San Diego, 46 Riverside, 79 Berkeley, 89 Davis, 117 Los Angeles, 120 Irvine, 128 Santa Barbara, 132 Santa Cruz, 144 Merced) plus the six largest CSU transfer destinations (11 Cal Poly San Luis Obispo, 26 San Diego State, 39 San Jose State, 42 Northridge, 81 Long Beach, 129 Fullerton).
UCSF is the one UC absent: it enrols no undergraduates and publishes no articulation agreements.
Every id is verified against the captured `institutions.json` by a test, because a typo'd id reads as an empty corridor only after the pair has been walked.

`MAX_MAJORS_PER_PAIR` was added in S9c against live data and REMOVED (set to `None`) in S9d.
Keyword matching is substring-based, so it over-selects badly: 32 of De Anza's 168 UCSD major reports match, because `business` catches "Business Analytics Minor" and `computer science` catches every CSE specialization.
S9c capped it at 6 to keep the first live fetch inside one evening.
That cap is not defensible past the first fetch: a student's major is either in the artifact or it is not, and a triage that answers "no articulation" only because the build skipped that agreement is a wrong answer dressed as a finding.
The constant stays optional rather than deleted so the corridor can be narrowed again with one edit and no redesign.

The selection is round-robin across the keyword families (`select_majors`), NOT a flat alphabetical cut, because under a cap the first six labels by name are six psychology specializations and no computer science at all.
Uncapped the round-robin no longer changes WHICH agreements are selected, only the order they are fetched in; it is kept for that reason and tested at both settings (`select_majors` takes a `limit` keyword defaulting to the constant).
Within a family the order is by label then key, so the selection is a pure function of the reports list; the demo pair is exempt from any cap and always takes every major.

Endpoint URL builders (paths verified in the spike doc, "Endpoints") live HERE rather than in `fetch.py`.
The walk needs both the builders and the fetcher, so keeping the builders beside the corridor constants is what makes the dependency one-way (`corridor` -> `fetch`) instead of circular, and it leaves `fetch.py` as a transport-agnostic polite cached fetcher with no ASSIST endpoint knowledge.

- `academic_years_url()` -> `https://www.assist.org/api/AcademicYears`
- `institutions_url()` -> `https://www.assist.org/api/institutions`
- `categories_url(receiving_id, sending_id, year_id)` -> `/api/agreements/categories?receivingInstitutionId=&sendingInstitutionId=&academicYearId=`
- `agreements_url(receiving_id, sending_id, year_id, category)` -> `/api/agreements?...&categoryCode=` with `category` a `Literal["major", "dept"]`
- `agreement_url(key)` -> `/api/articulation/Agreements?Key=<urllib.parse.quote(key, safe="")>`

Corridor walk (the fetch stage), locked order and selection rules:

1. Fetch academic years and institutions.
2. Sending side = every institution with `isCommunityCollege: true`, sorted by id (116 per the fixture; the authoritative filter per spike implication 5).
3. For each pair `(cc, target)` in (cc id asc, target id asc) order: fetch categories at `PREFERRED_YEAR_ID`; if the `major` category has `hasReports: false`, step the year id down by one, at most `YEAR_FALLBACK_DEPTH` times; record the year used per pair (spike implication 6); if no year in range has reports, record the pair as empty in the build report and continue.
4. Fetch the major reports list at the chosen year; select EVERY report whose `label` casefold-contains any `PINNED_MAJOR_KEYWORDS` entry, ordered round-robin across the keyword families and truncated to `MAX_MAJORS_PER_PAIR` if that constant is not `None`; for the demo pair select ALL major reports; fetch each selected agreement payload by `key`.
5. Demo pair only: also fetch the dept reports list and every RECEIVING-side dept agreement payload, i.e. the keys whose fifth segment is `Department` (`select_depts`); the `SendingDepartment` mirrors are out of scope for v1 per `agreement.schema.md` and are dropped before any payload fetch.
   Dept depth beyond the demo pair is cuttable major-depth per the plan; the sending-CC breadth is never cut.

Volume sanity, MEASURED by the completed S9d fetch and superseding every earlier estimate.
The four S9c targets cost 4,148 requests capped at 6 majors per pair; the full fifteen-target uncapped corridor cost **34,975 requests total, 30,827 of them new, in about 12 hours at ~1.3 s per request**.

One structural fact makes this arithmetic rather than a sample: the major reports list is IDENTICAL in length for every community college sending to a given target, and so is the pinned-keyword match count.
Matches per community college, by target: UCSD 32, SDSU 37, SJSU 25, CSUN 20, UCD 20, UCSC 20, UCM 22, UCLA 16, UCI 16, CSULB 14, UCB 13, UCR 12, UCSB 12, CPSLO 6, CSUF 5 - **270 agreements per community college**.

What the fetch actually produced:

| Quantity | S9c (4 targets, capped) | S9d (15 targets, uncapped) |
|---|---|---|
| pairs walked | 464 | 1,740 |
| agreements stored | 2,972 | 31,236 |
| articulations stored | 27,452 | 309,709 |
| `articulation.db` | 17 MB | **185 MB** |
| raw cache (gitignored) | 190 MB | 2.17 GB |

Every one of the 30,827 new requests answered HTTP 200: zero 429s across twelve hours, which is the S9c session-renewal rule (renew every 40 requests) holding at seven times the scale it was measured at.
Zero agreements were excluded, zero pairs hit a `scope_error`, and 15 of 1,740 pairs published no agreement in any year within `YEAR_FALLBACK_DEPTH`.

The fetch is fully resumable through the cache, so an interrupted run re-runs with the identical command and costs nothing for what it already has; only the artifact size is a standing decision (overview doc, "Permission gates").
The plan's original "2,300 requests, 40 minutes" assumed ~5 majors per pair and 1 s per request; both were optimistic.

`walk_corridor(fetcher, *, only_pair: tuple[int, int] | None = None) -> CorridorScope` returns what it saw, as frozen tuple-valued dataclasses that `report.py` folds into the build report; `only_pair` is the seam the build script's `--pair S:R` flag uses.

```python
AgreementRef(assist_key, category, label, sending_id, receiving_id, year_id)   # exactly normalize_agreement's arguments
FetchFailure(assist_key, reason_code, detail)
PairScope(sending_id, receiving_id, year_id | None, major_reports, major_selected,
          dept_reports, dept_selected, agreements, fetch_failures, scope_error | None)
CorridorScope(targets, sending_count, preferred_year_id, pairs)
```

Fault isolation in the walk, locked:

- A failed agreement payload fetch is recorded as a `FetchFailure` on its pair and the walk continues; one bad agreement never breaks the build.
- A failed categories or reports-list fetch ends that pair with `scope_error` set and the walk continues to the next pair.
- A `session_bootstrap_failed` is NOT isolated: it is a global condition, and swallowing it per pair would silently burn hundreds of requests, so it propagates out of the walk.

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

`advisement_texts(attributes: object) -> list[str]`, pinned in S9c from live payloads (overview doc, "Advisements: RESOLVED in S9c").
Absent or empty -> `[]`.
The pinned entry shape is `{"content": str, "position": int}`: text is taken verbatim apart from an outer strip, ordered by `position`, never merged or truncated.
ANYTHING else -> `AssistNormalizeError(advisement_shape_unknown)`, which the isolation loop records as that articulation's or group's exclusion; this covers the structurally different `NFollowing` selection rules template sections publish under the same field name.
Twelve levels feed it as of S9e: the four locked above, the three the S9c sweep added (`courseAttributes` on the articulation, `attributes` on template groups and cells), and five a FULL-corridor S9e sweep proved carry real prose the 364-payload S9c sample missed - `seriesAttributes` on the articulation, `attributes` on template sections and rows, and `courseAttributes`/`seriesAttributes` on template cells, the last carrying 41,246 corridor entries of the "Minimum grade required" family.
Two lists stay unread deliberately: `receivingAttributes` mirrors the articulation-level lists verbatim, and `requirementAttributes` sits only on `Requirement` cells, which already exclude their group.

Template assets (major agreements only; `templateAssets` null for dept):

- Keep only entries with `type == "RequirementGroup"`, sorted by `position`; `GeneralTitle`/`GeneralText` entries are dropped for v1 (prose, not requirements; recorded as a future enrichment, not built now).
- Per group: `instruction` null -> `conjunction = "And"`; `instruction.type == "Conjunction"` -> its `conjunction` value; `instruction.type == "Following"` with `selectionType == "Complete"` -> `conjunction = "And"`; the course-counting N-from slice -> `("Or", select_courses)` per the paragraph below; any other instruction shape -> exclusion `template_shape_unsupported` for that group (the agreement still stores).

`Following` was added to the supported set in S9d, after the fifteen-campus corridor measured it as the single largest exclusion in the artifact: 39,434 of 125,357 requirement groups, 31.5%.
Its payload carries exactly `{"type", "id", "selectionType"}` in every one of those instances - no `amount`, no `conjunction`, no selection semantics - and assist.org renders it as "Complete the following", against "Complete 8.00 semester units from the following" for `NFromArea` and "Complete 1 course from the following." for `NFromConjunction`.
Payload and rendered prose agree: it means complete all of these, which is what a null instruction already means.
`selectionType` is the gate, not decoration: 460 of the 39,434 corridor instances say `Select`, and those stay excluded because a selection rule is genuinely unmodeled.

The N-from family's course-counting slice was modeled in S9d and its semantics were CORRECTED in S9e against rendered agreements: `NFromConjunction`/`NFromArea`/`NFromFollowing` with `amountUnitType == "Course"`, `amountQuantifier` `None`/`AtLeast`, `toAmountDeterminer` `None`, and an area conjunction that is `Or`, absent, or inert maps to `RequirementGroupAsset.select_courses` = "complete at least N courses from the union of the group's sections".
The amount counts COURSES, never sections; an `NFromConjunction` whose own conjunction is `And` over several sections ("Complete 1 course from A and B") is ambiguous and stays excluded.
The full rationale, rendered-page evidence, and the excluded remainder live in `docs/specs/agreement.schema.md` and `docs/notes/articulation_spotchecks.md` section 11.
- Sections sorted by `position`; each section's rows sorted by `position`; every row must contain exactly one cell of `type == "Course"` or `type == "Series"` (S9d); anything else -> exclusion `template_shape_unsupported` for the group.
- Cell -> `TemplateCell(cell_id=cell["id"], course=... | series=...)`; advisement text is read from the group's `advisements` and `attributes`, each section's `advisements` and `attributes`, each row's `attributes`, and each cell's `attributes`, `courseAttributes`, and `seriesAttributes`, in that payload order (S9e).

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
     "major_reports": 168, "major_selected": 168, "dept_reports": 86, "dept_selected": 50,
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

- `UrllibTransport` against a stub opener: an `HTTPError` comes back as an `HttpResponse` carrying its status, a `URLError` propagates, headers and timeout pass through, `cookie_value` reads a real `CookieJar`.
- Fetcher against `FakeHttpTransport`: bootstrap sends the cookie header echo on API calls; missing cookie and non-200 bootstrap -> typed `session_bootstrap_failed`; 400 triggers exactly one re-bootstrap plus retry, second 400 -> typed failure naming the URL; a 429 renews the session and retries, a persistent 429 fails typed after exactly `MAX_SESSION_RENEWALS` renewals, the session renews proactively at `SESSION_REQUEST_BUDGET`, and a renewed session echoes the new token; another non-200, a non-JSON body, and a transport `URLError` -> typed `agreement_fetch_failed`; 1 req/s pacing via recorded sleeper (`sleeps` between two network calls >= 1.0); cache hit performs zero transport calls and zero sleeps; offline mode raises typed on miss and still serves a hit; manifest line written per network fetch, failures included; no error message contains the token or a response body.
- Corridor against `FakeHttpTransport` seeded from the seven captured fixtures: the url builders are byte-exact (including the percent-encoded agreement key); the demo pair resolves to year 76 with 168 major reports selected and 86 dept reports; keyword selection, year fallback, an exhausted fallback, an isolated agreement failure, an isolated reports-list failure, and the non-isolated session failure each have a case; two walks produce equal `CorridorScope` values.
- Static gates extended in `backend/tests/test_import_boundaries.py`: `urllib` is confined to `assist/http.py` plus `assist/corridor.py`, and no region package imports a sibling region (the testing strategy's planned import-boundary addition). `backend/tests/test_package.py` registers `starmap.assist`.
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
