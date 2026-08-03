# Frontend Increments: Overview

This folder plans the web API seam and the full Ascent frontend, turning the Week 2 "request loop" and Week 3 "polish" roadmap items into executable implementation plans.
One doc per increment, written for a less-capable executor model per `AGENTS.md` "Implementation Plan Conventions": every design decision is locked here; the executor implements and does not design.
Authored 2026-08-03; all cited symbols, file paths, and fixture facts verified against branch `feat/triage-costs-demo` at commit `df69561` on that date.

Authority order for an executing session: user chat instructions, `CLAUDE.md`, `AGENTS.md`, `docs/FOOTHOLD_PATHFINDERS_PLAN.md` + `docs/FOOTHOLD_TECH_REFERENCE.md`, these docs, `docs/specs/`, code.
"TR 4.4" means `docs/FOOTHOLD_TECH_REFERENCE.md` section 4.4 and is a binding pointer.
The binding visual spec is `docs/design/ASCENT.md`; the interactive mockup `docs/design/triage-board/Foothold Prototype.dc.html` (+ `support.js`) is the layout and copy reference for every screen.

## Backend readiness verdict (the input to this plan)

Ready and verified, requiring no changes beyond what these docs name:

| Piece | Where | State |
| --- | --- | --- |
| Deterministic evaluator | `transfer/evaluate.py` (`build_evaluation`, `sort_findings`, `AgreementBundle`, `CourseRequest`) | done, fixture-tested per reason code |
| Triage view-model | `transfer/triage.py` (`build_triage_board`, `TriageBoard`, `TriageHeader`) | done; `lib/evaluation.ts` mirrors it |
| Cost table | `transfer/costs.py` + `data/curated/costs.json` | done; missing target rate means `None` dollars, never zero |
| Fuzzy matcher | `retrieval/index.py` (`CourseIndex.search/lookup`), `retrieval/resolve.py` | done; `corpus.db` committed, 117 CCs indexed |
| Contracts + JSON schemas | `contracts/evaluation.py`, `contracts/reason_codes.py`, `backend/schemas/*.json` | done; frontend types mirror these |
| Demo ground truth | `data/curated/demo_students/deanza_ucsd_cs.json`, `docs/notes/evaluator_verification.md` | hand-verified against assist.org 2026-08-02 |
| LLM backbone | `llm/engine.py`, `llm/call_log.py`, `llm/transport_anthropic.py`, FakeTransport seam | done; no nodes built |

Missing entirely (this plan builds the first three; the LLM nodes are a separate plan folder):

1. The HTTP layer: `app/web/` holds two empty `__init__.py` files; `fastapi`/`uvicorn` are not dependencies; there is no route, session middleware, `sessions.db`, exception-handler stack, or SPA mount.
2. The frontend: no `frontend/`, no `package.json` anywhere.
3. Mode B arbitrage: no `transfer/arbitrage.py`.
4. `llm/transcript_parser.py` and `llm/petition_writer.py` (out of scope here; doc 05 defines their wire contracts so the UI and the nodes agree).

## Scope and dependency order

| Doc | Increment | Depends on |
| --- | --- | --- |
| `01-web-api.md` | FastAPI assembly, `sid` session, deterministic API surface, evaluation persistence | nothing new |
| `02-frontend-foundation.md` | Vite + React scaffold, Ascent tokens, `lib/` modules, parity fixtures | 01 (wire shapes) |
| `03-screens.md` | Landing, course entry, evaluation theater, triage board, wired end to end | 01, 02 |
| `04-arbitrage.md` | `transfer/arbitrage.py`, contract + endpoint, arbitrage tab UI | 01, 03 |
| `05-petition-parse-ui.md` | Petition drawer + transcript-paste LLM upgrade; wire contracts locked now, UI executed after the LLM nodes land | 03, plus the separate LLM-node increments |
| `SPLITS.md` | session splits with kickoff prompts and gates | all |

Cut-line mapping (plan doc, "Cut-lines"): 05 falls first (chips-only input still demos fully; the drawer button stays visibly disabled), then 04's UI (keep the API + a screenshot), then non-demo targets.

## Locked design-translation rules (prototype -> product)

The prototype adds flourishes beyond `ASCENT.md`; these deltas are decided here, once, and are not relitigated by executors.

1. No PRNG anywhere, per the determinism axiom in `CLAUDE.md`.
   The prototype's idle "holo flash" loop (`Math.random()` timers in `componentDidMount`) is DROPPED entirely.
   The pointer-driven foil sheen (a pure function of cursor position) is KEPT; it is deterministic input-driven presentation.
2. Foil CTA exception: the three gradient "foil" buttons (landing CTA, evaluate CTA, draft-petition CTA) are kept as a deliberate, bounded exception to Ascent's no-gradient rule, fixed to the `Gold` finish and `Prism lines` texture (no runtime finish switching).
   Everything else stays flat chalk/slate per `ASCENT.md`.
   This exception must be recorded as an amendment to `ASCENT.md` in the same commit as doc 03, and the amendment requires an explicit user OK at that split's kickoff; if declined, the buttons ship flat slate-on-chalk per the Ascent surface rules and nothing else changes.
3. The at-risk wall steps in the prototype use a chrome gradient fill; product uses `ASCENT.md`'s amber OUTLINED steps (chalk fill, 2px amber border).
   The teal secure step and the dashed final step translate as drawn.
4. Fonts are self-hosted via `@fontsource/archivo` (weights 400, 500, 800, 900); the prototype's Google Fonts `<link>` never ships (no external requests at runtime).
5. All motion (row stagger, step fill, count-up, drawer slide) is a pure function of the order-stable view-model, disabled under `prefers-reduced-motion`, exactly per `ASCENT.md` "Motion".
6. Verdicts always render shape + icon + word; dollar values of `None` render as absent (no dollar chip), never `$0`; every count renders as `N of M`.

## Locked API deltas from the plan doc

The plan doc's API sketch (`docs/FOOTHOLD_PATHFINDERS_PLAN.md:185-197`) predates the store's actual query surface; two deltas are locked here.

1. `GET /api/targets/{id}/majors` becomes `GET /api/pairs/{sending_id}/{receiving_id}/majors`.
   ASSIST agreements are per (sending, receiving, major); `ArticulationStore.load_agreements_for_pair` (`assist/store.py:187`) requires both ids, and the landing screen always knows both before the major picker fills.
2. `POST /api/evaluations` returns the full `Evaluation` contract JSON; there is no server-side board serialization.
   The triage board is a pure client-side projection (`lib/evaluation.ts` mirrors `transfer/triage.py`), so `TriageBoard`/`TriageHeader` dataclasses never need wire shapes.

## Dependency gates (standing decision point 3, `docs/IMPLEMENTATION_ROADMAP.md:97`)

Every new dependency needs the user's explicit OK at the split kickoff that introduces it:

- Backend (doc 01): `fastapi`, `uvicorn` (runtime); `httpx` (dev, for `TestClient`).
- Frontend (doc 02): `react`, `react-dom`, `@fontsource/archivo` (runtime); `typescript`, `vite`, `@vitejs/plugin-react`, `vitest`, `@types/react`, `@types/react-dom` (dev).
- Nothing else; no router, no state library, no CSS framework, no eslint/prettier in v1 (recorded as a deliberate deferral; `tsc --noEmit` via the build plus vitest is the frontend gate).
