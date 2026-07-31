# Agent Constitution

## Project Mission

Build Astrolabe (working name "Starmap"): a Columbia course-selection helper for the Stellic Pathfinders challenge.

Students onboard with their major, completed courses, interests, and career direction.
The system generates a few personalized, prerequisite-valid course pathways per major, each with grounded fit reasoning, rendered as an interactive star-atlas map.

Data: the Columbia College bulletin (~80 department pages) and the CULPA API (professor ratings and reviews, optional and degradable).

It is not a scheduler, a calendar product, a degree audit, or a generic chatbot.

## Core Thesis

**LLMs propose. Deterministic infrastructure disposes.**

Exactly two LLM nodes exist: the prereq extractor (build time) and the pathway proposer (request time).
Deterministic code owns everything else: retrieval, candidate pools, validation, repair limits, swap logic, caching, session state, cost logging, and every committed artifact.
This architecture is the originality hook and the through-line for the contest write-up.

## Contest Constraints

- Submission window: Jul 20 - Aug 21, 2026; every line in this repo must be newly written inside it.
- Agentic-Calendar (`/Users/shawnliu/Documents/Agentic-Calendar`) is a read-only design reference.
  Never copy file contents from it (official terms sections 6.1 and 9.2); re-implement smaller, purpose-built modules from the written design records.
- Track every AI tool used; the tools disclosure is mandatory and omission is a disqualification ground.
- Judging weighs equally: real student problem, originality, scalability, design/UX, build quality.

## Non-Negotiable Axioms

- No LLM anywhere in the retrieval path.
- No LLM output enters an artifact or response without deterministic validation.
- At most 2 repair attempts per artifact, then the typed fallback (prereqs: `fallback_flat`; pathways: drop the failing candidate, serve survivors).
- Every failure produces a typed `reason_code`.
- The vocabulary gate: the prompt's candidate pool and the validator's allowed set are the same object, never re-derived.
- Every LLM call is cost-logged with hashes only, never raw prompts or responses.
- `catalog.db` and `corpus.db` are committed, read-only build artifacts; `sessions.db` is the only mutable database.
- Contracts are frozen with `extra="forbid"`; updates rebuild through full validation.
- Committed generated artifacts regenerate byte-identically, enforced by `--check` in CI.
- Identity is the server-minted `sid` cookie; client-supplied user ids are always overwritten.
- `note` prereq leaves are never silently satisfied and are always surfaced in the UI.
- Frontend layout is deterministic: no PRNG, order-stable, `round1`-rounded.
- A failing department parse is excluded and reported, never allowed to break the build.
- Never cut "all departments scraped": it is the headline scalability claim.

## Required Reading Before Major Changes

- Product, architecture, milestones, risks, cut-lines: `STARMAP_PATHFINDERS_PLAN.md`
- Mechanism-level design record (schemas, invariants, algorithms, gotchas): `STARMAP_TECH_REFERENCE.md`
  - RAG pipeline: section 1
  - Pathway map and atlas layout: section 2
  - Onboarding: section 3
  - LLM engine, call log, SQLite kernel, app assembly, contracts conventions, testing seams: section 4
  - Recorded gotchas: the appendix
- The relevant schema contract in `docs/specs/` for any shape change.

Prefer the tech reference over browsing the Agentic-Calendar source.

## Development Rules

- Treat schemas in `docs/specs/` as contracts. Update specs before changing schema-related code.
- Keep LLM outputs structured. Prose explains decisions but is never the source of truth for validation, routing, or writes.
- Pass all proposed pathways through the deterministic validator before serving; violation codes are typed and fixture-tested.
- Preserve `run_id` and typed `reason_code` values across validation, service, and user-visible errors.
- Keep orchestration state explicit. Do not hide workflow state in prompts or LLM text.
- LLM SDK imports live only in `llm/`.
- Region packages do not import sibling regions; communicate through `contracts/` and `common/`.
- Keep re-implemented kernels minimal and purpose-built; do not carry over generality the reference code has and Starmap does not need.
- When scope pressure appears, follow the plan's cut-lines in order; do not invent new scope cuts silently.

## Writing And Craft Standards

- Never use the em dash "—". Use plain dash "-" instead.
- When writing commit messages, NEVER auto-add your agent name as co-author.
- Never manually modify CHANGELOG.md files or any files that are marked as auto-generated.
- When writing or substantially editing long Markdown files, put each full sentence on its own line.
  Preserve normal Markdown structure, but avoid wrapping multiple sentences onto one physical line.
- When making technical decisions, do not give much weight to development cost.
  Instead, prefer quality, simplicity, robustness, scalability, and long term maintainability.
- When doing bug fixes, always start with reproducing the bug in an E2E setting as closely aligned with how an end user would hit it.
  This makes sure you find the real problem so your fix will actually solve it.
- When end-to-end testing a product, be picky about the UI you see and be obsessed with pixel perfection.
  If something clearly looks off, even if it is not directly related to what you are doing, try to get it fixed along the way.
- Apply that same high standard to engineering excellence: lint, test failures, and test flakiness.
  If you see one, even if it is not caused by what you are working on right now, still get it fixed.

## Implementation Plan Conventions

When a new feature is proposed and planning docs are written before implementation:

- Plans live in a dedicated folder under `docs/implementation-plans/<feature>/`: numbered docs (`00-overview.md`, `01-…`) plus a `SPLITS.md`.
- Write plans for a less-capable executor model. Every design decision must be locked in the docs - formulas, weights, thresholds, store and plumbing choices, exact file and symbol references, and hard constraints not to be relitigated. The executor implements; it does not design.
- `SPLITS.md` must size the work into context-window splits of roughly **300k total session tokens or less** each - reads, edits, test iterations, and gate runs included - at planning time, not at execution time.
- Each split is one fresh Claude Code session ending in exactly one commit, with a copy-pasteable kickoff prompt naming the docs, source files, and tests to read, the branch to create, the hard constraints, and the gates that must be green before the commit.
- Budget honestly: account for fixed per-session overhead (`CLAUDE.md`, `AGENTS.md`, the plan folder, and the named source and test files, read before the first edit) and leave deliberate slack - a session dying mid-commit is the real failure mode. Oversized work gets more splits, and multi-phase splits should name an internal fallback commit boundary where the codebase is green and honest on its own.
- Verify cited line numbers against the target branch at planning time and date-stamp the verification; executors trust named symbols over line numbers when drift appears.
- A session that creates or amends planning docs must not end with them untracked: before wrapping up, surface the uncommitted paths and propose a docs-only commit on an appropriate branch. Plan folders left uncommitted across sessions and machines are a known failure mode (blocked pulls, stale local copies shadowing merged upstream versions).

## Testing Expectations

- Prereq expression evaluation and satisfiability have direct unit tests, including `note` leaves and unknown-term handling.
- Every pathway violation code has an invalid fixture that proves the validator fires it.
- The repair loop is tested against FakeTransport: retry pacing, attempt sequences, cap exhaustion, boundary revalidation of schema-enforced output.
- Session middleware tests cover cookie minting and the client-user-id-overridden trust boundary.
- Frontend lib modules (atlas layout, onboarding state, pathway/swap state) are vitest-covered; layout tests pin purity, a byte-stable snapshot, and order stability.
- Components have no tests; they must stay thin enough not to need them.
- Catalog build stages are testable on cached HTML with zero network; the parse report is reviewed after every full build.
- LLM-facing code is tested with fixtures, contracts, and pinned prompt hashes, never by trusting prompt wording.

## Deploy Verification Rules

- Target: Fly.io single machine; `catalog.db`/`corpus.db` baked read-only into the image; `sessions.db` on the `/data` volume; only secret is `ANTHROPIC_API_KEY`.
- A deploy is not done until the live URL passes a smoke check: `/healthz`, a cold pathway generation, and a cached regeneration.
- Green local tests are not evidence about production; verify against the live host.
- Pre-warm the demo profiles after every deploy; the demo video records against the live URL.

## Forbidden Shortcuts

- Do not let an LLM decide routing, validation outcomes, or confidence.
- Do not serve a pathway that has not passed the deterministic validator.
- Do not exceed 2 repair attempts per artifact.
- Do not treat invalid structured output as "good enough."
- Do not silently drop validation failures, retries, or departments.
- Do not put an LLM in the retrieval path or the swap path.
- Do not log raw prompts or responses; hashes and counts only.
- Do not hand-edit committed generated artifacts; regenerate them.
- Do not copy code from Agentic-Calendar, ever.
- Do not add sign-in, a scheduler, a calendar, or degree-audit claims.
