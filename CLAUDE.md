# Claude Operating Contract

This file is mandatory project context for Claude Code. Follow it strictly.

The repository authority order is:

1. User instructions in the current chat.
2. `CLAUDE.md`.
3. `AGENTS.md`.
4. `STARMAP_PATHFINDERS_PLAN.md` and `STARMAP_TECH_REFERENCE.md`.
5. `docs/specs/` and other design docs.
6. Existing code and tests.

If any instruction conflicts with the contest rules or the project axioms, stop and ask the user.

## Project Mission

Astrolabe (working name "Starmap") is a Columbia course-selection helper, built as an entry for the Stellic Pathfinders challenge (category: Degree Planning and Discovery).

Students onboard with their major, completed courses, interests, and career direction.
The system generates a few personalized course pathways per major, each a set of course nodes with grounded fit reasoning, rendered as an interactive star-atlas map.

It is not:

- a scheduler or calendar product;
- a degree audit (that is Stellic's core product; we sit upstream: discovery, not verification);
- a generic chatbot;
- a system where LLM prose controls workflow state.

Core thesis:

> LLMs propose. Deterministic infrastructure disposes.

LLMs generate structured candidates (prereq expression trees at build time, pathway proposals at request time).
Deterministic code owns validation, repair limits, retrieval, candidate pools, swap logic, session state, caching, cost logging, and every data artifact.

## Contest Rules (Non-Negotiable)

- Every line in this repo must be newly written during the submission window (Jul 20 - Aug 21, 2026).
- `/Users/shawnliu/Documents/Agentic-Calendar` is a READ-ONLY design reference.
  Study the reference files named in the plan; NEVER copy file contents from it (official terms sections 6.1 and 9.2).
- Do not modify the Agentic-Calendar repo.
- Track every AI tool used (Claude Code, Claude API, anything else); disclosure is mandatory and omission is a disqualification ground.
- Deliverables: title/category, 500-word write-up, 2-min demo video, working prototype link, tools list.

## Mandatory First Step

Before any substantive change, read:

- `STARMAP_PATHFINDERS_PLAN.md` (product, architecture, milestones, cut-lines);
- the relevant section of `STARMAP_TECH_REFERENCE.md` (mechanism-level design record: schemas, invariants, algorithms, gotchas);
- the relevant spec in `docs/specs/` if object shape, validation, serialization, fixtures, or generated schemas may change.

Prefer the tech reference over browsing the Agentic-Calendar source.
Do not edit first and read later.

## Permission Boundaries

Allowed without additional user confirmation:

- Read project files and Agentic-Calendar reference files.
- Edit project source, tests, docs, and fixtures when directly required by the user's request.
- Run local deterministic checks (tests, lint, typecheck, data-build dry runs on cached HTML).
- Add focused tests for changed behavior.
- Regenerate schemas or committed artifacts only when their sources intentionally change.

Ask the user before:

- Installing new dependencies or changing dependency versions.
- Running networked commands (bulletin fetches, CULPA API calls, LLM API calls, deploys).
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

- No LLM anywhere in the retrieval path: FTS5/BM25 only, deterministic over checked-in data.
- LLM output never enters an artifact or a response without deterministic validation.
- Exactly two LLM nodes: the prereq extractor (build time) and the pathway proposer (request time).
  Only `llm/` may import the LLM SDK.
- Repair is bounded: at most 2 repair attempts per artifact, then the typed fallback path (prereqs: `fallback_flat`; pathways: drop the failing pathway, serve the survivors).
- Every failure produces a typed `reason_code`; no silent drops.
- The vocabulary gate: the candidate course pool given to the proposer prompt IS the object the validator checks `unknown_course` against; one projection, two consumers, never a re-derivation.
- Every LLM call is logged with tokens, cost estimate, outcome, and hashes; never raw prompts or responses.
- `catalog.db` and `corpus.db` are committed build artifacts, read-only at runtime; `sessions.db` is the only mutable database.
- Contracts are frozen with `extra="forbid"`; updates rebuild through full validation, never `model_copy(update=...)`.
- Committed generated artifacts must regenerate byte-identically; every generator has a `--check` mode wired into CI.
- No sign-in: identity is the server-minted HttpOnly SameSite=Lax `sid` cookie; never trust a client-supplied user id.
- Prereq satisfiability is evaluated deterministically from validated expression trees; `note` leaves are never silently satisfied and are always surfaced in the UI.
- Frontend layout is deterministic: no PRNG, canonical viewport, `round1` rounding, order-stable output.
- Scraping is polite: 1 req/s, on-disk cache, per-dept fault isolation; a failing department is excluded, never breaks the build.

## Architecture Boundaries

Backend package boundaries (under `backend/src/starmap/`):

- `common/`: tiny shared kernel (sqlite, clock, ids, errors).
- `contracts/`: Pydantic models, one module per spec.
- `retrieval/`: corpus store, deterministic chunking, FTS5/BM25 index.
- `llm/`: the only LLM integration area (engine, call log, the two nodes).
- `catalog/`: bulletin fetch/parse, CULPA ingest, catalog store, build orchestration.
- `prereqs/`: expression evaluation and extraction validation.
- `pathways/`: candidate pool, prompt cards, validator, alternatives, cache, service.
- `app/web/`: FastAPI app, session middleware, routes.

Region packages must not import sibling regions; cross-region communication goes through `contracts/` and `common/`.

Frontend: all logic lives in React-free, unit-tested `lib/` modules (`lib/atlas/`, `lib/onboarding.ts`, `lib/pathway.ts`); screens and components are thin renderers with no component tests.

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

Add or update tests for changes touching:

- typed `reason_code` values and pathway violation codes;
- prereq expression evaluation and satisfiability;
- validator behavior, with one invalid fixture per violation code;
- the repair loop, against FakeTransport;
- session middleware and the trust boundary;
- layout determinism (purity, byte-stable snapshot, order stability);
- fixtures or contract behavior.

Use deterministic assertions.
Prompt wording is not a test oracle; use fixtures, contracts, and pinned prompt hashes.

## Local Commands

Run backend commands from `backend/` (uv-managed), frontend commands from `frontend/`.

Once bootstrapped, the expected targets are:

```bash
make build-data    # catalog + corpus build (cached HTML; network stages ask first)
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
- the change requires live network access (bulletin, CULPA, LLM provider, deploy);
- the implementation would require breaking package boundaries;
- the schema/spec implications are unclear;
- secrets or credentials are needed;
- existing uncommitted changes block a safe edit;
- tests reveal failures outside the scope of the task and the fix is not obvious.
