# LLM Node Increments: Session Splits

Sizing per `AGENTS.md`: each split is one fresh Claude Code session ending in exactly one commit, budgeted at roughly 300k total session tokens or less at planning time, overhead included (`CLAUDE.md`, `AGENTS.md`, this folder, named sources and tests read before the first edit).
N1 and N2 are independent of each other; both need PR #8 (`feat/arbitrage`) merged to `main` first.
N3 needs both, with a petition-only internal fallback if N2 was cut.
No new dependencies anywhere in this folder, so no dependency gates; live API calls stay behind the user's explicit go-ahead (the smoke script in N3 is the only live path, and nothing in `make check` touches it).

| Split | Doc | Branch | Est. tokens | Blockers |
| --- | --- | --- | --- | --- |
| N1 | 01-petition-writer.md | `feat/petition-writer-node` | ~260k | PR #8 merged |
| N2 | 02-transcript-parser.md | `feat/transcript-parser-node` | ~240k | PR #8 merged |
| N3 | 03-web-seam.md | `feat/llm-web-seam` | ~250k | N1 + N2 merged (petition-only fallback if N2 cut) |

Frontend split F5 (`docs/implementation-plans/frontend/SPLITS.md`) unblocks after N3 merges.

## N1 kickoff prompt

> Read `docs/implementation-plans/llm-nodes/00-overview.md` and `01-petition-writer.md`, then `backend/src/starmap/llm/{engine,call_log,errors,transport_anthropic}.py`, `backend/src/starmap/contracts/{evaluation,llm_call_log,reason_codes,codes,base}.py`, `backend/tests/llm/conftest.py`, `backend/tests/support/{transports,prompt_pins}.py`, `backend/tests/test_prompt_pins.py`, `backend/tests/fixtures/valid/evaluation/demo_shape.json`, and `docs/specs/evaluation.schema.md`.
> Create branch `feat/petition-writer-node`.
> Implement doc 01 exactly in contract-discipline order: `docs/specs/petition.schema.md`, `contracts/petition.py`, fixtures, regenerated schemas, `llm/petition_writer.py`, the FakeTransport suite, both prompt-pin layers.
> Hard constraints: the bundle contains selected findings only; the citation vocabulary is computed from the bundle and nothing else; the template letter must pass its own citation validator; only `repair_limit_exceeded` falls back, every other `GenerationError` is a typed `failed`; `write_petition` never raises; no network, no new dependencies.
> Gates before the single commit: `make check` green.

## N2 kickoff prompt

> Read `docs/implementation-plans/llm-nodes/00-overview.md` and `02-transcript-parser.md`, then `backend/src/starmap/llm/{engine,call_log,errors,transport_anthropic}.py`, `backend/src/starmap/retrieval/resolve.py` (the `Resolution` vocabulary you must mirror, not import), `backend/src/starmap/contracts/{cc_course,codes,base,reason_codes}.py`, `backend/tests/llm/conftest.py`, `backend/tests/support/{transports,prompt_pins}.py`, `backend/tests/test_prompt_pins.py`, and `backend/tests/app/conftest.py` (the demo course set for the paste fixture).
> Create branch `feat/transcript-parser-node`.
> Implement doc 02 exactly in contract-discipline order: `docs/specs/transcript_parse.schema.md`, `contracts/transcript_parse.py`, fixtures, regenerated schemas, `llm/transcript_parser.py`, `data/curated/demo_students/deanza_ucsd_cs_paste.txt`, the FakeTransport suite, both prompt-pin layers.
> Hard constraints: `llm/` never imports `retrieval/` (the `ChipResolver` Protocol is the seam); resolution never triggers repair and unresolved entries never become chips; only `course_code` is grounded, via the stripped-casefold containment rule; `parse_transcript` never raises; no network, no new dependencies.
> Gates before the single commit: `make check` green.

## N3 kickoff prompt

> Precondition check first: confirm `llm/petition_writer.py` and `llm/transcript_parser.py` exist on main with green FakeTransport suites; if only the petition node exists, execute the petition-only fallback boundary named in doc 03 and say so.
> Read `docs/implementation-plans/llm-nodes/00-overview.md` and `03-web-seam.md`, then `backend/src/starmap/app/web/{app,routes,store,errors,session,config}.py`, the two node modules and their tests, `backend/src/starmap/llm/call_log.py`, `backend/src/starmap/retrieval/{index,resolve}.py`, `backend/tests/app/conftest.py`, and doc 05's "Locked wire contracts" as amended (`sending_institution_id` on the parse body).
> Create branch `feat/llm-web-seam`.
> Implement doc 03 exactly: the two stores with the pending-TTL rule, the two error types, the four routes with the locked status-code order, the background job functions with the catch-all `failed` guard, the shared `sessions.db` connection, the `llm_transport` parameter with the env-key gate, `backend/scripts/smoke_llm.py`, and the two test files.
> Hard constraints: 202-then-poll with the uniform-404 session boundary; LLM failure after repair exhaustion is HTTP 200 with `status: "failed"` (petition fallback is `succeeded` + `fallback: true`); `make check` must pass with no `ANTHROPIC_API_KEY` set; the smoke script never runs in CI or tests; live calls only on my explicit go-ahead.
> Gates before the single commit: `make check`, `npm run build`, `npm test` green; offer me the smoke-script run as a separate, explicitly-approved step.

## Standing rule

Per `AGENTS.md`, a session that amends these planning docs must surface the uncommitted paths before it ends and propose a docs-only commit; do not leave this folder untracked.
