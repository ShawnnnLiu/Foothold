# LLM Node Increments: Overview

This folder plans the two request-time LLM nodes (`llm/petition_writer.py`, `llm/transcript_parser.py`) and the web seam that exposes them, completing the Week 2 roadmap line "transcript parser + petition writer -> app/web".
One doc per increment, written for a less-capable executor model per `AGENTS.md` "Implementation Plan Conventions": every design decision is locked here; the executor implements and does not design.
Authored 2026-08-03; all cited symbols, file paths, and fixture facts verified against branch `feat/arbitrage` at commit `e976795` on that date.
That branch is PR #8 into `main`; these increments execute on top of `main` after it merges, and the kickoff prompts assume that merge happened.

Authority order for an executing session: user chat instructions, `CLAUDE.md`, `AGENTS.md`, `docs/FOOTHOLD_PATHFINDERS_PLAN.md` + `docs/FOOTHOLD_TECH_REFERENCE.md`, these docs, `docs/specs/`, code.
"TR 4.1" means `docs/FOOTHOLD_TECH_REFERENCE.md` section 4.1 and is a binding pointer.
The binding product definition of both nodes is `docs/FOOTHOLD_PATHFINDERS_PLAN.md:145-162`; the binding wire contracts are `docs/implementation-plans/frontend/05-petition-parse-ui.md` as amended by this folder (see "The one wire amendment" below).

## Backend readiness verdict (the input to this plan)

Ready and verified, requiring no changes beyond what these docs name:

| Piece | Where | State |
| --- | --- | --- |
| Generation engine, bounded repair | `llm/engine.py` (`GenerationEngine`, `AdapterConfig`, `Transport`, `TransportResult`) | done; tested against FakeTransport |
| Call log | `llm/call_log.py` (`SqliteCallLogStore`, `CallLogStore`), `contracts/llm_call_log.py` (`LlmNode` already carries both node values) | done |
| Production transport | `llm/transport_anthropic.py` (`AnthropicTransport`, `build_client`, `SONNET_5_INPUT_PRICE_PER_MTOK`, `SONNET_5_OUTPUT_PRICE_PER_MTOK`) | done; the only SDK import site |
| Typed errors | `llm/errors.py` (`GenerationError`, `TransportError`) | done |
| FakeTransport seam | `backend/tests/support/transports.py` (`FakeTransport`, `success`, `malformed`, `truncated`, `refusal`) | done |
| Prompt pins, layer 1 | `backend/tests/test_prompt_pins.py` (`SYSTEM_PROMPT_PINS`, seeded empty) | done; node increments add one row each |
| Prompt pins, layer 2 | `backend/tests/support/prompt_pins.py` (`capture_prompt_frames`, `assert_prompt_pin`) | done; node increments instantiate per node |
| Course resolver | `retrieval/resolve.py` (`resolve_course`, `Resolution`, `FUZZY_ACCEPT_RATIO`), `retrieval/index.py` (`CourseIndex`) | done; result vocabulary is exactly `exact` / `fuzzy_match` / `unresolved` |
| Findings object | `contracts/evaluation.py` (`Evaluation`, `Finding`, `Citation`), `docs/specs/evaluation.schema.md` | done; the petition vocabulary gate's single projection |
| Web seam | `app/web/` (app assembly, `SidMiddleware`, `EvaluationStore`, exception handlers, uniform 404) | done for the deterministic surface |
| App-test harness | `backend/tests/app/conftest.py` (`build_app_config`, `demo_body`, De Anza -> UCSD fixture pair) | done; reused by increment N3 |

Missing entirely (this plan builds all of it):

1. `contracts/petition.py` and `contracts/transcript_parse.py` with their specs, fixtures, and generated JSON schemas.
2. `llm/petition_writer.py`: findings bundle, prompt, citation validator, deterministic template letter, the node service.
3. `llm/transcript_parser.py`: prompt, groundedness post-validator, resolution disposal, the node service.
4. The web seam: two job stores, four routes, background execution, transport wiring, the LLM-unavailable gate.

## Scope and dependency order

| Doc | Increment | Depends on |
| --- | --- | --- |
| `01-petition-writer.md` | N1: petition contract stack + `llm/petition_writer.py` | PR #8 merged |
| `02-transcript-parser.md` | N2: transcript-parse contract stack + `llm/transcript_parser.py` | PR #8 merged (independent of N1) |
| `03-web-seam.md` | N3: job stores, routes, wiring, live smoke script | N1 + N2 merged (internal fallback: petition-only seam if N2 was cut) |
| `SPLITS.md` | session splits with kickoff prompts and gates | all |

The petition writer comes FIRST, deliberately.
The plan doc's cut-line order (`docs/FOOTHOLD_PATHFINDERS_PLAN.md`, "Cut-lines") sacrifices the transcript-parse node before anything else, while the petition letter is the demo climax.
Building N1 before N2 means a schedule collapse still leaves the letter in hand; N3 carries an internal fallback boundary that ships the petition seam alone.
Frontend split F5 (`docs/implementation-plans/frontend/SPLITS.md`) blocks on this folder and consumes the wire contracts exactly as locked.

## The one wire amendment (decided here, applied to doc 05 in this folder's commit)

`05-petition-parse-ui.md` locked `POST /api/transcript/parse` with body `{"text": str}` and no institution.
That contract cannot be implemented: resolution runs against one CC's `cc_courses` projection, and `resolve_course` requires `institution_id`.
Amendment, locked now: the body is `{"text": str, "sending_institution_id": int}` with `sending_institution_id > 0`, named identically to `EvaluationRequestBody.sending_institution_id` in `app/web/routes.py`.
Doc 05 is edited in the same commit that lands this folder, so F5 never sees the stale shape.
Nothing else in doc 05's locked contracts changes.

## Locked cross-cutting decisions

These are decided once, here, and are not relitigated by executors.

1. Package boundaries.
   The two node modules live in `llm/` and import only `contracts/`, `common/`, and `llm/` internals.
   `llm/` never imports `retrieval/` (sibling-region rule, `CLAUDE.md`): the transcript parser receives resolution through a `ChipResolver` Protocol defined in `llm/transcript_parser.py`, and the composition root (`app/web/app.py` + `app/web/routes.py`) adapts `retrieval.resolve.resolve_course` to it.
   This mirrors TR 3.6: the intake node "never imports the taxonomy kernel; aliases arrive as a plain mapping from the composition root".
2. Engine configuration, per node, defined as a module constant beside each node:

   | | `PETITION_WRITER_CONFIG` | `TRANSCRIPT_PARSER_CONFIG` |
   | --- | --- | --- |
   | `model_name` | `"claude-sonnet-5"` | `"claude-sonnet-5"` |
   | `prompt_version` | `"petition-writer-v2"` (v1 at landing; bumped 2026-08-04 with the prompt amendment recorded in doc 01) | `"transcript-parser-v1"` |
   | `max_tokens` | `3000` | `8000` |
   | prices | the two `SONNET_5_*_PRICE_PER_MTOK` constants imported from `llm/transport_anthropic.py` | same |
   | everything else | `AdapterConfig` defaults (retries 2, repairs 2, timeout 300, backoff 1.0) | same |

   `max_tokens` rationale, recorded: a letter is capped at 8000 characters (roughly 2000 tokens) plus JSON envelope; a 60-course proposal at roughly 50 output tokens per course plus envelope stays under 8000.
   Extended thinking is already pinned off in the transport, so `max_tokens` is pure output budget.
3. Run identity.
   The job id IS the engine `run_id`: `parse_...` ids come from `IdGenerator.new_id("parse")` and `pet_...` ids from `IdGenerator.new_id("pet")` (doc 05 names both prefixes).
   `SqliteCallLogStore.list_for_run(job_id)` therefore returns exactly one job's provider calls, which is what the smoke script prints.
4. Outcome-to-wire mapping, both nodes (the 200-with-`status: "failed"` policy from `CLAUDE.md`):

   | Engine outcome | Transcript parse result | Petition result |
   | --- | --- | --- |
   | validated model | `succeeded` (resolution then runs; unresolved entries are content, not failure) | `succeeded`, `fallback: false` |
   | `GenerationError` with `repair_limit_exceeded` | `failed` + that reason code (the deterministic path is the user's own chips; there is no synthetic transcript) | `succeeded`, `fallback: true`, that reason code, the deterministic template letter |
   | any other `GenerationError` (`auth_failed`, `rate_limited`, `call_failed`, `retry_limit_exceeded`, `refusal`, `truncated`, `malformed_output`, `schema_rejected` as terminal codes) | `failed` + its reason code | `failed` + its reason code |

   Node services NEVER raise: each returns its typed result contract, and every failure carries the `GenerationError`'s reason code.
   No new `LlmReasonCode` members are needed; the family in `docs/specs/reason_codes.schema.md` already covers every outcome above.
5. Job execution model.
   Both POST routes insert a `pending` row, schedule the node run via FastAPI `BackgroundTasks`, and return 202 with the job id; Starlette runs the sync task in its threadpool after the response.
   The shared-`SqliteDatabase` `RLock` (TR 4.3) serializes the background writer against request readers.
   A process death mid-job leaves a `pending` row forever; the client's 30-second poll cap (doc 05) bounds the user-facing wait, and the pending-duplicate check (decision 6) stops a stuck row from blocking retries.
   No job queue, no worker process, no new dependency: one Fly.io machine, two demo-scale nodes.
6. Pending-duplicate suppression (petitions only, per doc 05's 409).
   `selection_key = ",".join(str(p) for p in sorted(finding_positions))`, stored on the petition row.
   A POST whose `(sid, evaluation_id, selection_key)` matches a `pending` row younger than `PENDING_TTL_SECONDS = 120` gets 409; an older pending row is treated as abandoned and a new job starts.
   120 seconds is four times the client poll cap, so a live job is never falsely abandoned.
7. One `sessions.db` connection.
   `create_app` currently constructs `SqliteDatabase(config.sessions_db)` inline for `EvaluationStore`; N3 hoists it to a single shared instance passed to `EvaluationStore`, both job stores, and `SqliteCallLogStore`, so all four share one lock and one WAL file.
   Each store keeps its own `ensure_schema` component triple; `sessions.db` remains the only mutable database.
8. The LLM availability gate.
   `create_app(config, llm_transport=None)` gains a keyword-only transport parameter.
   Production (`dev_app`, deploy): when the parameter is `None`, the transport is `AnthropicTransport(build_client())` if `ANTHROPIC_API_KEY` is set in the environment, else the LLM surface is disabled.
   Disabled means: both POST routes raise `LlmUnavailableError` (a `StarmapError` with `reason_code="llm_unavailable"`, added to `PRECONDITION_ERRORS`), surfacing as 409, and the rest of the app is untouched.
   Tests always pass a `FakeTransport`, so `make check` stays zero-network and green with no key present.
   Live calls remain behind the user's explicit go-ahead: nothing in this plan runs a networked command; the user supplies the key and runs the smoke script or the server themselves.
9. Canonical serialization for prompt-bound JSON.
   Everywhere a dict is rendered into a prompt (the petition findings bundle), the bytes are `json.dumps(bundle, sort_keys=True, indent=2)`.
   Determinism here is what makes the layer-2 prompt pins byte-stable.
10. Prompt-pin discipline (TR 4.6), both layers, both nodes.
    Layer 1: one `PromptPin` row per system-prompt constant in `backend/tests/test_prompt_pins.py`.
    Layer 2: one pinned-frames test per node using `capture_prompt_frames` with a script whose first response fails deterministically, plus rot guards (`must_contain` / `must_exclude`) named in each node doc.
    An intentional prompt edit bumps `prompt_version` and replaces the pin in the same commit; prompt wording is never a test oracle beyond these pins.

## Cost expectation (recorded for the AI-disclosure budget)

At `claude-sonnet-5` list price ($3.00 / $15.00 per MTok): a worst-case transcript parse (20,000 characters, roughly 5k input tokens, three repair attempts) stays under $0.15; a petition draft (roughly 2k input tokens, 800 output tokens, three attempts) stays under $0.10.
Every call logs `cost_estimate_usd` through the existing engine; the smoke script prints the per-run total from `list_for_run`.
