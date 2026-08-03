# Claude Operating Contract

This file is mandatory project context for Claude Code. Follow it strictly.

The repository authority order is:

1. User instructions in the current chat.
2. `CLAUDE.md`.
3. `AGENTS.md`.
4. `docs/FOOTHOLD_PATHFINDERS_PLAN.md` and `docs/FOOTHOLD_TECH_REFERENCE.md`.
5. `docs/specs/` and other design docs.
6. Existing code and tests.

If any instruction conflicts with the contest rules or the project axioms, stop and ask the user.

## Project Mission

Foothold is a transfer credit navigator for the California community college to UC/CSU corridor, built as an entry for the Stellic Pathfinders challenge (category: Overcoming Obstacles).
Pivoted from the Columbia course-selection helper on 2026-07-31 and renamed from Astrolabe to Foothold on 2026-08-01; see the pivot and rename notices in `docs/FOOTHOLD_PATHFINDERS_PLAN.md`.

Mode A (headline): a student picks their community college, target university, and major, enters their courses (chips or pasted transcript), and gets a deterministic triage of their credits against the official ASSIST articulation agreement: transfers cleanly / at risk / no articulation, plus requirements still owed and a grounded draft petition letter for credits at risk.
Mode B: gen-ed arbitrage, the same articulation index inverted to find community-college courses that articulate back to an enrolled student's degree, ranked by cost saved.
Mode C (stretch tier, pre-cut): the legacy course-pathway framework, retargeted to pre-transfer planning; build only on explicit user go-ahead.

It is not:

- a degree audit (that is Stellic's core product; we sit upstream and pre-application: protection before enrollment, verification after);
- an advising chatbot;
- a scheduler or calendar product;
- a system where LLM prose controls workflow state or decides transferability.

Core thesis:

> LLMs propose. Deterministic infrastructure disposes.
> The AI never decides what transfers; the articulation agreement does.

LLMs translate at the two human edges only (transcript text in, petition letter out), both request-time.
Deterministic code owns the build pipeline (no LLM stage at all), the transfer verdict, validation, repair limits, retrieval, arbitrage, session state, caching, cost logging, and every data artifact.

## Contest Rules (Non-Negotiable)

- Every line in this repo must be newly written during the submission window (Jul 20 - Aug 21, 2026).
- `/Users/shawnliu/Documents/Agentic-Calendar` is a READ-ONLY design reference.
  Study the reference files named in the plan; NEVER copy file contents from it (official terms sections 6.1 and 9.2).
- Do not modify the Agentic-Calendar repo.
- Track every AI tool used (Claude Code, Claude API, anything else); disclosure is mandatory and omission is a disqualification ground.
- Deliverables: title/category, 500-word write-up, 2-min demo video, working prototype link, tools list.

## Mandatory First Step

Before any substantive change, read:

- `docs/FOOTHOLD_PATHFINDERS_PLAN.md` (product, architecture, milestones, cut-lines);
- the relevant section of `docs/FOOTHOLD_TECH_REFERENCE.md` (mechanism-level design record: schemas, invariants, algorithms, gotchas);
- the relevant spec in `docs/specs/` if object shape, validation, serialization, fixtures, or generated schemas may change.

Prefer the tech reference over browsing the Agentic-Calendar source.
Do not edit first and read later.

## Permission Boundaries

Allowed without additional user confirmation:

- Read project files and Agentic-Calendar reference files.
- Edit project source, tests, docs, and fixtures when directly required by the user's request.
- Run local deterministic checks (tests, lint, typecheck, data-build dry runs on cached ASSIST JSON).
- Add focused tests for changed behavior.
- Regenerate schemas or committed artifacts only when their sources intentionally change.

Ask the user before:

- Installing new dependencies or changing dependency versions.
- Running networked commands (ASSIST fetches, LLM API calls, deploys).
- Creating commits, pushing branches, or opening pull requests.
- Deleting files or moving large groups of files.
- Changing public contracts, schemas, or architecture beyond the stated task.
- Changing project rules, `AGENTS.md`, or this file.
- Running commands that write outside the repository.

Never do these unless the user explicitly requests the exact action:

- `git reset --hard`, `git clean`, `git checkout -- <path>`
- force push or rewriting history
- deleting untracked work
- modifying secrets, credentials, tokens, or `.env` files
- copying file contents from Agentic-Calendar into this repo
- bypassing tests, hooks, or validation to make a change appear complete

## Non-Negotiable Axioms

- No LLM anywhere in the transfer verdict, the retrieval path, or the build pipeline: evaluation and FTS5/BM25 are deterministic over checked-in data, and the articulation build has no LLM stage.
- LLM output never enters an artifact or a response without deterministic validation.
- Exactly two LLM nodes, both request-time: the transcript parser and the petition writer.
  Only `llm/` may import the LLM SDK.
- Repair is bounded: at most 2 repair attempts per artifact, then the typed fallback path (transcript: unresolved chips surfaced for manual fix; petition: deterministic template letter).
- Every failure produces a typed `reason_code`; no silent drops.
- The vocabulary gate, twice: the `cc_courses` projection used by UI autocomplete IS the set the transcript validator resolves against, and the deterministic findings object given to the petition prompt IS the set the citation validator checks the letter against; one projection, two consumers, never a re-derivation.
- Every LLM call is logged with tokens, cost estimate, outcome, and hashes; never raw prompts or responses.
- `articulation.db` and `corpus.db` are committed build artifacts, read-only at runtime; `sessions.db` is the only mutable database.
- Contracts are frozen with `extra="forbid"`; updates rebuild through full validation, never `model_copy(update=...)`.
- Committed generated artifacts must regenerate byte-identically (SQLite artifacts: canonical logical dump); every generator has a `--check` mode wired into CI.
- No sign-in: identity is the server-minted HttpOnly SameSite=Lax `sid` cookie; never trust a client-supplied user id.
- Articulation satisfaction is evaluated deterministically from validated expression trees; `note` leaves (advisements) are never silently satisfied: they downgrade a match to at-risk and are always surfaced in the UI.
- Every finding carries its citation (agreement key, articulation position, year) so the UI and the petition letter cite ground truth.
- Frontend rendering is deterministic: no PRNG in layout, data, or workflow state; order-stable view-models, stable sort keys.
  Sole exception (2026-08-03, explicit user decision): the triage wall's ambient "chance event" flashes are PRNG-timed presentation-only effects, per the third amendment in `docs/design/ASCENT.md`.
- Fetching is polite: 1 req/s, on-disk cache, per-agreement fault isolation; a failing agreement is excluded and reported, never breaks the build.

## Architecture Boundaries

Backend package boundaries (under `backend/src/starmap/`; the package keeps the legacy codename `starmap`):

- `common/`: tiny shared kernel (sqlite, dbdump, clock, ids, errors).
- `contracts/`: Pydantic models, one module per spec.
- `retrieval/`: FTS5/BM25 index over `cc_courses` for fuzzy course resolution.
- `llm/`: the only LLM integration area (engine, call log, transcript parser, petition writer).
- `assist/`: ASSIST fetch, normalize, store, build orchestration.
- `transfer/`: the deterministic evaluator, triage view-model, arbitrage.
- `pathways/`: Mode C stretch tier; stays empty unless the user green-lights Mode C.
- `app/web/`: FastAPI app, session middleware, routes.

The pre-pivot `catalog/` and `prereqs/` packages are renamed/absorbed into `assist/` and `transfer/` during the articulation increments.
Region packages must not import sibling regions; cross-region communication goes through `contracts/` and `common/`.

Frontend: all logic lives in React-free, unit-tested `lib/` modules (`lib/evaluation.ts`, `lib/courses.ts`); screens and components are thin renderers with no component tests.

Do not allow prompts, prose explanations, or LLM text to become control-plane state.

## Schema And Contract Rules

Treat `docs/specs/` as contracts between LLM nodes and deterministic services.

Before changing object shape or semantics:

1. Read the relevant `docs/specs/*.schema.md`.
2. Update the spec first.
3. Update the Pydantic contract model.
4. Update valid and invalid fixtures.
5. Update generated JSON schemas if applicable.
6. Update tests.

Rules:

- Reject invalid LLM output before consumers use it; schema-enforced output must still be boundary-revalidated.
- Preserve `run_id` and typed `reason_code` values across layers.
- Every field constraint and model validator has a named invalid fixture that proves it fires.

## HTTP Policy

- LLM/workflow failure after repair exhaustion: HTTP 200 with `status: "failed"` and a typed `reason_code`.
- Contract-invalid request: 422 via the global `ValidationError` handler (registered before the `ValueError` handler).
- Command-precondition failure: 409.
- Every HTML document is served `Cache-Control: no-cache`; public HTML routes accept HEAD; the SPA catch-all mounts last.

## Testing Requirements

Before writing any test, read `docs/TESTING_STRATEGY.md`.
It defines the suite's layer structure (static, unit/contract, integration seams, minimal E2E) and which layer a new test belongs in.

Add or update tests for changes touching:

- typed `reason_code` values and evaluation finding codes;
- `articulation_expr` evaluation (including partial-series and note/advisement semantics);
- evaluator and citation-validator behavior, with one named fixture per reason code;
- the repair loop, against FakeTransport;
- session middleware and the trust boundary;
- view-model determinism (purity, order stability);
- fixtures or contract behavior.

Use deterministic assertions.
Prompt wording is not a test oracle; use fixtures, contracts, and pinned prompt hashes.

## Local Commands

Run backend commands from `backend/` (uv-managed), frontend commands from `frontend/`.

Once bootstrapped, the expected targets are:

```bash
make build-data    # articulation + corpus build (cached ASSIST JSON; network stages ask first)
make test          # pytest
make lint typecheck
make check         # everything CI runs
```

Frontend: `npm test` (vitest), `npm run build`.
Keep this section updated as the real Makefile and scripts land.

## Git Rules

Assume the working tree may contain user changes.

- Check status before commits.
- Do not revert changes you did not make.
- Do not delete untracked files unless the user explicitly asks.
- Do not create commits, push, amend, or rewrite history unless the user explicitly asks.
- Commit at the end of every increment when the user has asked for autonomous execution.
- NEVER auto-add your agent name as co-author in commit messages.

## Working Style

Prefer small, directly scoped changes.

Before editing: identify the relevant contract, spec, or existing pattern; inspect nearby tests; understand current behavior.

During implementation: preserve architecture boundaries; keep structured data structured; keep kernels minimal and purpose-built (no unused generality); follow the plan's cut-lines when scope pressure appears.

After implementation: run the narrowest meaningful checks first, then broader ones for shared behavior; report commands run and failures honestly; state any remaining risk.

## Stop Conditions

Stop and ask the user if:

- a requested change conflicts with a contest rule or a non-negotiable axiom;
- the change requires live network access (ASSIST, LLM provider, deploy);
- the implementation would require breaking package boundaries;
- the schema/spec implications are unclear;
- secrets or credentials are needed;
- existing uncommitted changes block a safe edit;
- tests reveal failures outside the scope of the task and the fix is not obvious.
