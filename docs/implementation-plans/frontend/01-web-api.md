# Increment F1: The Web API Seam

Goal: a runnable FastAPI app exposing the deterministic API surface over the committed artifacts, with the `sid` session, evaluation persistence in `sessions.db`, and the full HTTP policy, so the frontend has a real backend to wire against.
Binding mechanism references: TR 4.4 (app assembly order and its three load-bearing reasons), TR 4.3 (`common/sqlite.py`), the HTTP policy in `CLAUDE.md`, and the API section of `docs/FOOTHOLD_PATHFINDERS_PLAN.md` with the two deltas locked in `00-overview.md`.

New dependencies (user gate at kickoff): `fastapi`, `uvicorn` runtime; `httpx` dev.
No other new packages; in particular no ORM, no `python-multipart`, no settings library.

## Files (exact list)

| File | Contents |
| --- | --- |
| `backend/src/starmap/app/web/config.py` | `AppConfig` frozen dataclass: `articulation_db`, `corpus_db`, `sessions_db`, `costs_path`, `dist_dir`, `secure_cookies: bool`; `load_config()` reading env `FOOTHOLD_ARTICULATION_DB`, `FOOTHOLD_CORPUS_DB`, `FOOTHOLD_SESSIONS_DB`, `FOOTHOLD_COSTS`, `FOOTHOLD_DIST`, `FOOTHOLD_SECURE_COOKIES` with repo-relative defaults (`data/articulation.db`, `data/corpus.db`, `data/sessions.db`, `data/curated/costs.json`, `frontend/dist`, false) |
| `backend/src/starmap/app/web/session.py` | the `sid` middleware |
| `backend/src/starmap/app/web/store.py` | `EvaluationStore` over `sessions.db` |
| `backend/src/starmap/app/web/bundles.py` | `load_bundle(store, sending, receiving, major_key)` MOVED from `backend/scripts/evaluate_student.py:68`; the script now imports it from here (scripts sit outside region boundaries, so the import is legal; `app` is the composition root and may import `assist`, `transfer`, `retrieval`) |
| `backend/src/starmap/app/web/routes.py` | one `APIRouter` with every `/api/*` route |
| `backend/src/starmap/app/web/app.py` | `create_app(config: AppConfig) -> FastAPI` in the pinned assembly order; `main.py` style `uvicorn` entry via `make run` |
| `backend/src/starmap/app/web/errors.py` | `error_body(error, type, reason_code=None)` helper plus the handler registrations |
| `backend/tests/app/` | tests per the list below |

`sessions.db` is created lazily on first write, lives outside the repo image contract (`CLAUDE.md`: the only mutable database), and is gitignored (add `data/sessions.db*` to `.gitignore`).

## Session middleware (locked)

- Cookie name `sid`, value minted via `UuidIdGenerator.new_id("sid")` (`common/ids.py`), so the format is `sid_<hex>`.
- On every request: read the cookie; if absent or not matching `^sid_[0-9a-f]+$`, mint a fresh id and set the cookie on the response: `HttpOnly`, `SameSite=Lax`, `Path=/`, `Secure` iff `config.secure_cookies`.
- A well-formed unknown sid is accepted as-is; it owns no evaluations, so it can read nothing.
- The trust boundary: identity is ONLY this cookie; no request body or header may name a user or session id, and the store filters every read by the middleware-derived sid.
- No canonical-host redirect middleware in v1 (single Fly host later; recorded deferral from TR 4.4 step 4).

## App assembly order (TR 4.4, adapted)

1. `app.state`: open `articulation.db` and `corpus.db` read-only via `common/sqlite.py`; construct `ArticulationStore`, `CourseIndex`, `load_cost_table`, `EvaluationStore`, `UuidIdGenerator`, the real clock.
2. Session middleware.
3. `GET /healthz` (and HEAD) returning `{"status": "ok"}`; never behind other middleware concerns.
4. Exception handlers, most-specific first: `StarmapError` subclasses carrying a precondition semantic (see below) = 409; `StarmapError` = 400; pydantic `ValidationError` = 422; `ValueError` = 400.
   The TR 4.4 trap is binding: pydantic's `ValidationError` IS a `ValueError` subclass; register the `ValidationError` handler explicitly and test that an invalid body yields 422, not 400.
   Precondition set for 409 in this increment: `InstitutionNotIndexedError`, `Fts5UnavailableError` (`retrieval/errors.py`), and `UnknownAgreementError` (new, in `app/web/errors.py`, subclassing `StarmapError` with `reason_code="unknown_agreement"`).
   Every error body is `error_body(...)` = `{"error": str, "type": str, "reason_code": str | None}`.
5. The API router.
6. LAST: the SPA mount, only if `config.dist_dir / "index.html"` exists: `/assets` static mount, then a `GET|HEAD /{path:path}` catch-all serving a real top-level file when present (resolved and confined to `dist_dir`, path-traversal checked) else `index.html`; every HTML response carries `Cache-Control: no-cache` (hashed `/assets` exempt).
   When `dist_dir` has no build, non-API paths 404 cleanly (the API-only test posture from TR 4.4).

## Routes (locked shapes)

Request models are pydantic with `extra="forbid"` and live in `routes.py` (they are HTTP-layer shapes, not domain contracts; the domain contracts stay in `contracts/`).
All list responses are wrapped in an object (`{"institutions": [...]}`), never a bare array.

### `GET /api/institutions?kind=cc|target`

- `kind=cc`: `Institution.kind == "cc"`; `kind=target`: kind in `{"uc", "csu"}`; missing/other kind = 422.
- Row shape `{assist_id, code, name, kind}` from `ArticulationStore.load_institutions` (`assist/store.py:173`), sorted by `name` then `assist_id`.

### `GET /api/pairs/{sending_id}/{receiving_id}/majors`

- `load_agreements_for_pair(sending_id, receiving_id)` filtered to `category == "major"`, sorted by `label` then `assist_key`.
- Row shape `{assist_key, label, year_label}` (`year_label` = `academic_year_label`).
- Empty list is a valid 200 (the pair has no published major agreements).

### `GET /api/cc/{institution_id}/courses?q=`

- `q` required, min length 1 after strip, else 422; `k` fixed at 8 server-side (no client override).
- `CourseIndex.search(institution_id, q, k=8)`; row shape `{course_code, title, units_min, units_max}` in index order (the deterministic `-bm25, code` order from `retrieval/index.py`).
- Unindexed institution surfaces the 409 from `InstitutionNotIndexedError`.

### `POST /api/evaluations` (synchronous, deterministic)

Body:

```json
{
  "sending_institution_id": 113,
  "receiving_institution_id": 7,
  "major_key": "76/113/to/7/Major/...",
  "courses": [{"course_code": "MATH 1A"}]
}
```

- `courses` min length 1, max length 60; codes are uppercased and stripped server-side; duplicates after normalization = 422 with a message quoting the duplicate.
- The route never trusts client units or titles.
  It builds the vocabulary and units from `load_cc_courses(sending_institution_id)` (`assist/store.py:226`): `vocabulary = frozenset(codes)`, and each request becomes `CourseRequest(course_code, units=row.units_min, title=row.title)` when the code is in the vocabulary, else `CourseRequest(course_code)` (which `build_evaluation` turns into a typed `unresolved` finding; `transfer/evaluate.py:494-505`).
  `units_min` is the locked choice: it matches the evaluator's own conservative cell accounting (`_cell_units`, `transfer/evaluate.py:440`).
- Bundle via `bundles.load_bundle`; an unknown `major_key` for the pair raises `UnknownAgreementError` = 409.
  Bundles are cached in-process in a plain dict keyed `(sending, receiving, major_key)`; the DBs are read-only, so the cache never invalidates.
- Call `build_evaluation(requests=..., vocabulary=..., bundle=..., id_generator=app.state.ids, clock=app.state.clock, cost_table=app.state.costs)` and persist: `EvaluationStore.put(sid, evaluation)`.
- Response 200: `evaluation.model_dump(mode="json")`, exactly the `Evaluation` contract, nothing added.

### `GET /api/evaluations/{evaluation_id}`

- `EvaluationStore.get(sid, evaluation_id)`; wrong or unknown id, or another session's id, is uniformly 404 (`error_body("evaluation not found", "not_found")`); never reveal existence across sessions.

## `EvaluationStore` (locked)

- Table `evaluations(evaluation_id TEXT PRIMARY KEY, sid TEXT NOT NULL, created_at TEXT NOT NULL, payload TEXT NOT NULL)` plus index on `sid`.
- `put` stores `evaluation.model_dump_json()`; `get` revalidates through `Evaluation.model_validate_json` before returning (rebuild-through-validation, TR 4.5).
- Schema created via the same idempotent bootstrap pattern `common/sqlite.py` already supports; `SqliteCallLogStore` will share this database file in the LLM-node increments.

## Make targets and CI

- `make run`: `cd backend && uv run uvicorn starmap.app.web.app:dev_app --reload --port 8000`, where `dev_app` is a module-level `create_app(load_config())`.
- `make check` must stay green with zero network and without `data/articulation.db` present (CI never runs `make unpack-data`).
  Locked resolution: `create_app` opens its databases eagerly (lazy opening would hide misconfiguration until the first request), and every test constructs `AppConfig` pointing at tmp-path fixture databases, so `make check` never opens `data/articulation.db`.
- CI is unchanged in this increment (`make check` already runs the new tests).

## Testing (all under `backend/tests/app/`, TestClient, zero network)

Fixture helper `tests/app/conftest.py`: build a minimal `articulation.db`-shaped store and `corpus.db` index into `tmp_path` using the same store/index write APIs the build pipeline uses, seeded from `backend/tests/fixtures/assist/` payload fixtures (mirror how `tests/transfer/scenarios.py` builds bundles); yield a `TestClient` over `create_app(AppConfig(...))`.

1. `test_assembly.py`: `/healthz` GET and HEAD; unknown `/api/x` is JSON 404; with no `dist_dir` build, `/anything` 404s; with a fake `dist/index.html`, the catch-all serves it with `Cache-Control: no-cache` and a traversal attempt (`/../secret`) stays confined.
2. `test_session.py`: first response mints a `sid_` HttpOnly SameSite=Lax cookie; the same client keeps it; a malformed cookie is re-minted; session A cannot `GET` session B's evaluation (404).
3. `test_handlers.py`: an invalid `POST /api/evaluations` body is 422 (proving the `ValidationError`-before-`ValueError` ordering); an unknown major key is 409 with `reason_code: "unknown_agreement"`; an unindexed institution on autocomplete is 409 with `institution_not_indexed`.
4. `test_routes.py`: institutions filter by kind; majors list for the fixture pair; autocomplete returns index order and respects `q` validation; `POST /api/evaluations` for the fixture student returns an `Evaluation` that round-trips `Evaluation.model_validate`, with duplicate-code 422 and unresolved-code findings covered; `GET` returns the stored evaluation byte-identically.

Gates for this increment: `make check` green; `make run` + a manual `curl` of the five routes against the real committed data succeeds for the demo pair (sending 113, receiving 7, the major key in `docs/notes/evaluator_verification.md`), and the returned units match the verified numbers (clean 34.0, at risk 5.0, no articulation 4.5, still owed 10.0; dollars 1455.00 and 1309.50).
