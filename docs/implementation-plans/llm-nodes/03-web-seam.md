# Increment N3: LLM Web Seam

Goal: expose both nodes over the four wire routes doc 05 locks (as amended by `00-overview.md`), with session-scoped job stores, background execution, transport wiring, and the LLM-unavailable gate.
Binding references: doc 05 "Locked wire contracts", the HTTP policy in `CLAUDE.md`, TR 4.3/4.4, and decisions 3 through 8 in `00-overview.md`.

Internal fallback commit boundary (per `AGENTS.md`): if increment N2 was cut or the session runs long, the petition seam alone (stores, the two petition routes, wiring, tests) is a legal standalone commit; the parse routes then land in a follow-up split.

## Files

| Path | Content |
| --- | --- |
| `backend/src/starmap/app/web/store.py` | Add `TranscriptParseStore` and `PetitionStore` beside `EvaluationStore`. |
| `backend/src/starmap/app/web/errors.py` | Add `LlmUnavailableError` and `PetitionPendingError`; extend `PRECONDITION_ERRORS`. |
| `backend/src/starmap/app/web/routes.py` | Two request models, four routes, two background job functions, the resolver adapter. |
| `backend/src/starmap/app/web/app.py` | Shared `sessions.db` connection, call-log store, engines, the `llm_transport` parameter. |
| `backend/scripts/smoke_llm.py` | The live, user-gated smoke script. |
| `backend/tests/app/test_llm_routes.py` | The route suite against FakeTransport-backed nodes. |
| `backend/tests/app/test_llm_stores.py` | Store behavior including the pending-TTL rule. |

## Stores (`app/web/store.py`)

Both follow the `EvaluationStore` pattern exactly: own `(component, version, statements)` triple, canonical model JSON payload, reads revalidate through the contract, `get(sid, id)` returns `None` for unknown OR other-session ids (uniform 404).

`TranscriptParseStore`: component `"transcript_parses"`, version 1.

```sql
CREATE TABLE IF NOT EXISTS transcript_parses (
    parse_id TEXT PRIMARY KEY, sid TEXT NOT NULL,
    created_at TEXT NOT NULL, payload TEXT NOT NULL)
CREATE INDEX IF NOT EXISTS transcript_parses_by_sid ON transcript_parses (sid)
```

Methods: `put(sid, parse)` inserts; `finish(parse)` is `UPDATE transcript_parses SET payload = ? WHERE parse_id = ?` (the background task's only write); `get(sid, parse_id) -> TranscriptParse | None`.

`PetitionStore`: component `"petitions"`, version 1.

```sql
CREATE TABLE IF NOT EXISTS petitions (
    petition_id TEXT PRIMARY KEY, sid TEXT NOT NULL,
    evaluation_id TEXT NOT NULL, selection_key TEXT NOT NULL,
    created_at TEXT NOT NULL, payload TEXT NOT NULL)
CREATE INDEX IF NOT EXISTS petitions_by_sid ON petitions (sid)
CREATE INDEX IF NOT EXISTS petitions_by_selection ON petitions (sid, evaluation_id, selection_key)
```

Methods: `put(sid, petition)` inserts with `selection_key` computed by the module-level function `selection_key(finding_positions) = ",".join(str(p) for p in sorted(positions))`; `finish(petition)` updates payload by id; `get(sid, petition_id)`; `pending_exists(sid, evaluation_id, selection_key, *, now) -> bool` returns true when a row with that key has a payload whose `status == "pending"` AND `created_at` is within `PENDING_TTL_SECONDS = 120` of `now` (decision 6; the constant lives in `store.py`).
`pending_exists` parses payloads of the matching key only (at most a handful of rows) and stays inside one `read()` block.

## Errors (`app/web/errors.py`)

```python
class LlmUnavailableError(StarmapError):
    # raised by the POST routes when the app was built without a transport
    def __init__(self) -> None:
        super().__init__(
            "LLM features are disabled: no transport is configured (set ANTHROPIC_API_KEY)",
            reason_code="llm_unavailable",
        )

class PetitionPendingError(StarmapError):
    def __init__(self, evaluation_id: str) -> None:
        super().__init__(
            f"a petition for this selection on {evaluation_id} is already pending",
            reason_code="petition_pending",
        )
```

Both are appended to `PRECONDITION_ERRORS`, so they surface as 409 with the existing `precondition_failed` body; the free-form `reason_code` strings follow the `unknown_agreement` precedent.
No `LlmReasonCode` change.

## Wiring (`app/web/app.py`)

1. Hoist the sessions connection: `sessions = SqliteDatabase(config.sessions_db)` constructed once, passed to `EvaluationStore`, `TranscriptParseStore`, `PetitionStore`, and `SqliteCallLogStore` (decision 7).
2. New signature: `create_app(config: AppConfig, *, llm_transport: Transport | None = None)`.
   Resolution order: the parameter if given; else `AnthropicTransport(build_client())` when `os.environ.get("ANTHROPIC_API_KEY")` is non-empty; else `None`.
3. When a transport exists, build one engine per node and store them on state:

```python
app.state.call_log = SqliteCallLogStore(sessions)
app.state.parses = TranscriptParseStore(sessions)
app.state.petitions = PetitionStore(sessions)
app.state.llm = None if transport is None else LlmServices(
    transcript_engine=GenerationEngine(
        "transcript_parser", TranscriptProposal, TRANSCRIPT_PARSER_CONFIG,
        transport, app.state.call_log, app.state.clock, app.state.ids),
    petition_engine=GenerationEngine(
        "petition_writer", PetitionDraft, PETITION_WRITER_CONFIG,
        transport, app.state.call_log, app.state.clock, app.state.ids),
)
```

`LlmServices` is a frozen dataclass in `app/web/app.py`.
The stores and the call log are constructed unconditionally, so polling and history work even when generation is disabled.

## Routes (`app/web/routes.py`)

Request models, HTTP-layer shapes with `extra="forbid"`:

```python
class ParseRequestBody(BaseModel):
    text: str = Field(min_length=1, max_length=20000)
    sending_institution_id: int = Field(gt=0)

class PetitionRequestBody(BaseModel):
    finding_positions: list[int] = Field(min_length=1, max_length=60)
    # each item ge=0; model_validator: find_duplicates rejects repeats
```

### `POST /api/evaluations/{evaluation_id}/petition` -> 202 `{"petition_id": ...}`

1. Load the evaluation via `state.evaluations.get(request.state.sid, evaluation_id)`; `None` -> the uniform 404 JSON (`error_body("evaluation not found", "not_found")`), exactly like `get_evaluation`.
2. Validate positions against the stored findings: any position `>= len(evaluation.findings)`, or referencing a finding whose `bucket` is not `at_risk` or `no_articulation`, raises `RequestValidationError` (the manual-raise pattern `autocomplete_courses` uses) -> 422 naming the offending positions.
3. `state.llm is None` -> raise `LlmUnavailableError` (409).
4. `state.petitions.pending_exists(...)` -> raise `PetitionPendingError` (409).
5. Resolve prompt strings from the articulation store: institution names via `load_institutions()` filtered by the evaluation's two ids; `major_label` via `load_agreements_for_pair(...)` matching `assist_key == evaluation.major_key`.
   These lookups cannot miss for a stored evaluation; a miss is a programming error and may raise.
6. Mint `petition_id = state.ids.new_id("pet")`; `put` a `pending` `Petition` row (positions sorted ascending, `created_at = state.clock.now()`); schedule `run_petition_job` on `BackgroundTasks`; return 202.

### `GET /api/petitions/{petition_id}`

`state.petitions.get(sid, petition_id)`; `None` -> uniform 404.
Response body, exactly doc 05's poll shape: `{"status", "reason_code", "fallback", "letter_text", "cited"}` where `cited` items are `{"course_code", "finding_position"}` dicts; internal fields (`petition_id`, `evaluation_id`, `finding_positions`, `created_at`) are NOT serialized onto the wire.

### `POST /api/transcript/parse` -> 202 `{"parse_id": ...}`

1. `state.llm is None` -> `LlmUnavailableError` (409).
2. The institution must be indexed: call `state.index.search(body.sending_institution_id, ...)`-adjacent validation is wrong (a search is not a probe); instead reuse the existing precondition error by letting the resolver raise `InstitutionNotIndexedError` at job time is also wrong (the 409 must happen before the 202).
   Locked: probe with `state.articulation.load_cc_courses(body.sending_institution_id)`; an empty projection raises `InstitutionNotIndexedError` (already in `PRECONDITION_ERRORS`) -> 409.
3. Mint `parse_id`; `put` a `pending` `TranscriptParse` row; schedule `run_parse_job`; return 202.

### `GET /api/transcript/{parse_id}`

`state.parses.get(sid, parse_id)`; `None` -> uniform 404.
Wire body: `{"status", "reason_code", "chips", "unresolved"}` with chips serialized as doc 05's `{course_code, title, units_min, units_max, resolution}` and unresolved as `{proposed_code, proposed_title}`.

### Background job functions

Module-level functions in `routes.py`, taking `(state, ...)` explicitly (no request object; the response has already gone out):

```python
def run_parse_job(state, *, parse_id, sid, sending_institution_id, text) -> None
def run_petition_job(state, *, petition_id, sid, evaluation, finding_positions,
                     sending_name, receiving_name, major_label) -> None
```

Each calls its node service (`parse_transcript` / `write_petition`) and writes the result via `finish`.
Each wraps its whole body in `try/except Exception`: an unexpected exception finishes the row as `failed` with `reason_code=LlmReasonCode.CALL_FAILED` (belt over the services' never-raise contract; no silent pending row).
The parse job's resolver adapter is built here: `chip_resolver(index, institution_id)` returns a closure calling `retrieval.resolve.resolve_course(index, institution_id, code=code, title=title)` and mapping `Resolution` -> `TranscriptChip | None` (`status == "unresolved"` -> `None`; otherwise fields copy one-for-one with `status` -> `resolution`).
`app/web` importing `retrieval` and `llm` is the composition root doing its job; `llm/` itself stays retrieval-free (decision 1).

## The live smoke script (`backend/scripts/smoke_llm.py`)

User-gated: the script refuses to run without `ANTHROPIC_API_KEY` set and prints what it will call before doing it; nothing in `make check` executes it.
Behavior: build the production transport, run `parse_transcript` over `data/curated/demo_students/deanza_ucsd_cs_paste.txt` against the committed `corpus.db`, run a demo evaluation via `build_evaluation` and `write_petition` over its at-risk and no-articulation findings, print both results plus the per-run cost totals from `SqliteCallLogStore.list_for_run` against a throwaway temp database.
This is the manual live gate for the whole folder and the pre-warm rehearsal for deploy.

## Tests

`backend/tests/app/test_llm_stores.py`: put/finish/get round-trips revalidating through contracts; cross-session `get` returns `None`; `pending_exists` true inside the TTL, false past `PENDING_TTL_SECONDS` (drive with an explicit `now`), false once finished; duplicate insert raises.

`backend/tests/app/test_llm_routes.py`, over the existing `build_app_config` harness with `create_app(app_config, llm_transport=FakeTransport(script))`:

| Test | Pins |
| --- | --- |
| petition happy path | POST -> 202 with `pet_` id; GET -> `succeeded`, letter present, `cited` non-empty, only doc-05 keys on the wire. |
| petition fallback | Script of three rejected drafts -> GET shows `succeeded`, `fallback` true, `reason_code == "repair_limit_exceeded"`, the template letter. |
| petition failed | Scripted auth error -> GET shows `failed` + `"auth_failed"`, letter null (200 status, per the HTTP policy). |
| petition 404s | Unknown evaluation id and another session's evaluation id both -> uniform 404 on POST; unknown petition id -> 404 on GET. |
| petition 422s | Empty positions, duplicate positions, out-of-range position, position naming a `transfers_clean` finding. |
| petition 409 pending | Second identical POST while the first row is pending -> 409 `petition_pending` (drive by making `finish` not run: schedule against a script that raises after the row insert is observable, or stub the clock; the store-level TTL test covers timing). |
| parse happy path | POST with the curated paste text -> 202 `parse_` id; GET -> chips match the demo courses, `resolution` values correct. |
| parse failed | Exhaustion script -> `failed` + `"repair_limit_exceeded"`, empty lists. |
| parse 409 unindexed | `sending_institution_id` = the harness's `UNINDEXED_CC` (4) -> 409. |
| parse 422s | Empty text, text over 20000 chars, missing `sending_institution_id`, institution id 0. |
| llm disabled | `create_app` with no transport and no env key: both POSTs -> 409 `llm_unavailable`; GET polling still serves stored rows. |
| session isolation | A second client's cookie cannot read the first client's parse or petition. |
| call log rows | After a petition run, `list_for_run(petition_id)` is non-empty and every row's `node == "petition_writer"`. |

TestClient runs background tasks synchronously inside the request cycle, so polls in these tests observe final states; the `pending` wire shape is covered by the store tests and the contract fixtures, and this limitation is noted in the test module docstring rather than fought with threads.

## Gates

`make check` green with no `ANTHROPIC_API_KEY` in the environment (proves the zero-network seam); `npm run build` and `npm test` untouched but run once to confirm no frontend drift; the smoke script exists but runs only on the user's explicit go-ahead.
