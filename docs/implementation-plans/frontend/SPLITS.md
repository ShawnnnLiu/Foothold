# Frontend Increments: Session Splits

Sizing per `AGENTS.md`: each split is one fresh Claude Code session ending in exactly one commit, budgeted at roughly 300k total session tokens or less at planning time, overhead included (`CLAUDE.md`, `AGENTS.md`, this folder, named sources and tests read before the first edit).
Splits F1-F4 are sequential; F5 additionally blocks on the LLM-node increments (separate plan folder, not yet written).
Dependency installs inside a split need the user's explicit OK before `uv add` / `npm install` runs; the kickoff prompts say so.

| Split | Doc | Branch | Est. tokens | Blockers |
| --- | --- | --- | --- | --- |
| F1 | 01-web-api.md | `feat/web-api` | ~220k | user OK: fastapi, uvicorn, httpx |
| F2 | 02-frontend-foundation.md | `feat/frontend-foundation` | ~200k | F1 merged; user OK: npm dependency set |
| F3 | 03-screens.md | `feat/frontend-screens` | ~280k | F2 merged; user decision: ASCENT foil amendment |
| F4 | 04-arbitrage.md | `feat/arbitrage` | ~200k | F3 merged |
| F5 | 05-petition-parse-ui.md | `feat/petition-parse-ui` | ~260k | F3 merged + both LLM nodes merged |

## F1 kickoff prompt

> Read `docs/implementation-plans/frontend/00-overview.md` and `01-web-api.md`, then `docs/FOOTHOLD_TECH_REFERENCE.md` sections 4.3-4.6, `backend/src/starmap/transfer/evaluate.py` (the `build_evaluation` seam), `backend/src/starmap/assist/store.py`, `backend/src/starmap/retrieval/index.py`, `backend/scripts/evaluate_student.py`, `backend/src/starmap/common/{sqlite,ids,errors}.py`, and `backend/tests/transfer/scenarios.py` (the fixture-store pattern to mirror).
> Create branch `feat/web-api`.
> Ask me for the go-ahead before adding fastapi/uvicorn/httpx, then implement doc 01 exactly: config, session middleware, evaluation store, bundles move, routes, assembly order, error helper, and the four test files.
> Hard constraints: assembly order per TR 4.4 including the ValidationError-before-ValueError trap; identity only from the `sid` cookie; responses for `POST /api/evaluations` are the bare `Evaluation` contract; `make check` must pass with no `data/articulation.db` present.
> Gates before the single commit: `make check` green; `make run` + manual curl of all routes for the demo pair matching `docs/notes/evaluator_verification.md` numbers.

## F2 kickoff prompt

> Read `docs/implementation-plans/frontend/00-overview.md` and `02-frontend-foundation.md`, then `docs/design/ASCENT.md`, `backend/src/starmap/transfer/triage.py`, `backend/schemas/evaluation.schema.json`, `docs/specs/reason_codes.schema.md`, and `backend/scripts/evaluate_student.py`.
> Create branch `feat/frontend-foundation`.
> Ask me for the go-ahead before `npm create vite` and the dependency set, then implement doc 02 exactly: scaffold, tokens, `lib/api.ts`, `lib/evaluation.ts`, `lib/courses.ts`, `lib/format.ts`, `backend/scripts/dump_demo_fixtures.py` with `--check` wired into `make check`, the committed parity fixtures, the three vitest files, and the CI frontend job.
> Hard constraints: wire field names stay snake_case; `buildTriageBoard` mirrors `build_triage_board` with no re-sorting; fixtures are byte-deterministic via the repo's dump recipe.
> Gates: `npm run build`, `npm test`, and `make check` all green.

## F3 kickoff prompt

> Read `docs/implementation-plans/frontend/00-overview.md` and `03-screens.md`, then `docs/design/ASCENT.md`, `docs/design/triage-board/Foothold Prototype.dc.html` with `support.js`, and `frontend/src/lib/*` from F2.
> Create branch `feat/frontend-screens`.
> First decision gate: confirm or decline the ASCENT.md foil-button amendment from `00-overview.md` rule 2; on decline use flat slate CTAs.
> Implement doc 03 exactly: app shell state machine, the seven components, the four screens, wired to the live API.
> Hard constraints: no PRNG and no idle-flash loop; every animation parameter a pure function of view-model position; components thin, logic only in `lib/`; verdicts shape + icon + word; `None` dollars omitted, never `$0`.
> Internal fallback commit boundary: landing + entry + theater wired and green is a legal standalone commit if the session runs long; the triage board then lands in a follow-up split.
> Gates: `npm run build`, `npm test`, `make check` green; the manual E2E walk in doc 03 against `docs/notes/evaluator_verification.md`, including the reduced-motion pass and the built-SPA-through-FastAPI check.

## F4 kickoff prompt

> Read `docs/implementation-plans/frontend/00-overview.md` and `04-arbitrage.md`, then `docs/specs/evaluation.schema.md`, `backend/src/starmap/transfer/{evaluate,triage,costs}.py`, `backend/tests/transfer/scenarios.py`, and the prototype's Arbitrage section.
> Create branch `feat/arbitrage`.
> Implement doc 04 exactly in contract-discipline order: spec doc, `contracts/arbitrage.py`, fixtures, regenerated schemas, `transfer/arbitrage.py`, the route, the tab UI, and the tests.
> Hard constraints: no LLM anywhere; recompute satisfaction with `evaluate_expr`, never by parsing findings; `None` rates yield `None` dollars and an omitted count, never zero or a silent drop; server ranking is never re-sorted client-side.
> Gates: `make check`, `npm run build`, `npm test` green; manual spot-check of the top three demo rows against assist.org and the exact `units * (291 - 46)` math.

## F5 kickoff prompt

> Precondition check first: confirm `llm/petition_writer.py` and `llm/transcript_parser.py` exist on main with green FakeTransport suites; STOP and tell me if not.
> Read `docs/implementation-plans/frontend/00-overview.md` and `05-petition-parse-ui.md`, then the two node modules and their tests, `docs/FOOTHOLD_PATHFINDERS_PLAN.md:145-162`, and the prototype's Petition drawer section.
> Create branch `feat/petition-parse-ui`.
> Implement doc 05 exactly: the two route pairs to the locked wire contracts, the drawer, the parse upgrade including the `resolution` field on the evaluation request, and the tests.
> Hard constraints: 200-with-status-failed policy for repair exhaustion; letter underlines only from the server's `cited` list; unresolved parse entries never auto-become chips; live API calls stay behind my explicit go-ahead.
> Gates: `make check`, `npm run build`, `npm test` green; the manual demo-letter walk plus one forced-fallback run.

## Standing rule

Per `AGENTS.md`, a session that amends these planning docs must surface the uncommitted paths before it ends and propose a docs-only commit; do not leave this folder untracked.
