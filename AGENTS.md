# Agent Constitution

## Project Mission

Build Foothold: a transfer credit navigator for the California community college to UC/CSU corridor, entered in the Stellic Pathfinders challenge (category: Overcoming Obstacles).
The backend Python package keeps the legacy codename `starmap`.
Pivoted from the Columbia course-selection helper on 2026-07-31 and renamed from Astrolabe to Foothold on 2026-08-01; `docs/FOOTHOLD_PATHFINDERS_PLAN.md` is the product plan.

Mode A (headline): community college + target + major + the student's courses in, deterministic triage against the official ASSIST articulation agreement out (transfers cleanly / at risk / no articulation / still owed), with a grounded draft petition letter for credits at risk.
Mode B: gen-ed arbitrage, the same articulation index inverted and ranked by cost saved.
Mode C (stretch, pre-cut): the legacy pathway framework retargeted to pre-transfer planning; requires explicit user go-ahead.

Data: the ASSIST articulation API (all California community colleges to a pinned target list) and a curated per-unit cost table.

It is not a degree audit, an advising chatbot, a scheduler, or a calendar product.

## Core Thesis

**LLMs propose. Deterministic infrastructure disposes.**
**The AI never decides what transfers; the articulation agreement does.**

Exactly two LLM nodes exist, both request-time: the transcript parser (messy human input in) and the petition writer (grounded human output out).
The build pipeline has no LLM stage: ASSIST serves structured JSON, and the transfer verdict is deterministic evaluation over checked-in articulation data.
Deterministic code owns everything else: retrieval, evaluation, triage, arbitrage, validation, repair limits, caching, session state, cost logging, and every committed artifact.
This architecture is the originality hook and the through-line for the contest write-up.

### The Two LLM Planes

Development-time agents and product LLM nodes are different planes; never conflate them.

- Development plane: Claude Code (Fable 5, plus any subagents) writes the software in this repo.
  It never parses a transcript or drafts a petition by hand; it builds the pipeline that does.
- Product plane: the two LLM nodes run as Anthropic API calls through `llm/engine.py` (the only SDK import site), on the deployed server, pinned to `claude-sonnet-5`.
  This is what keeps parsing reproducible, cost-logged, bounded-repair, and runnable on redeploy without an interactive agent session.

## Contest Constraints

- Submission window: Jul 20 - Aug 21, 2026; every line in this repo must be newly written inside it.
- Agentic-Calendar (`/Users/shawnliu/Documents/Agentic-Calendar`) is a read-only design reference.
  Never copy file contents from it (official terms sections 6.1 and 9.2); re-implement smaller, purpose-built modules from the written design records.
- Track every AI tool used; the tools disclosure is mandatory and omission is a disqualification ground.
- Judging, five equally weighted criteria: does it solve a real student problem; is it original; how much could it help students if it scaled; the design and experience; how well it's built.

## Non-Negotiable Axioms

- No LLM anywhere in the transfer verdict, the retrieval path, or the build pipeline.
- No LLM output enters an artifact or response without deterministic validation.
- At most 2 repair attempts per artifact, then the typed fallback (transcript: unresolved chips surfaced for manual fix; petition: deterministic template letter).
- Every failure produces a typed `reason_code`.
- The vocabulary gate: the prompt's allowed set and the validator's allowed set are the same object, never re-derived (transcript resolution against the `cc_courses` projection; petition citations against the findings object).
- Every LLM call is cost-logged with hashes only, never raw prompts or responses.
- `articulation.db` and `corpus.db` are committed, read-only build artifacts; `sessions.db` is the only mutable database.
- Contracts are frozen with `extra="forbid"`; updates rebuild through full validation.
- Committed generated artifacts regenerate byte-identically, enforced by `--check` in CI.
  For SQLite artifacts (`articulation.db`, `corpus.db`), identity is defined over the canonical logical dump (schema plus rows in deterministic order), not raw file bytes, because raw bytes vary across SQLite library versions.
- Identity is the server-minted `sid` cookie; client-supplied user ids are always overwritten.
- `note` leaves (ASSIST advisements) are never silently satisfied: they downgrade a match to at-risk and are always surfaced in the UI.
- Every finding carries its citation (agreement key, articulation position, year); the petition letter may only cite what the findings contain.
- Frontend view-models are deterministic: no PRNG, order-stable, stable sort keys.
- A failing agreement parse is excluded and reported, never allowed to break the build.
- Never cut "all California community colleges on the sending side": it is the headline scalability claim; only per-pair major depth is cuttable.

## Required Reading Before Major Changes

- Product, architecture, milestones, risks, cut-lines: `docs/FOOTHOLD_PATHFINDERS_PLAN.md`
- Mechanism-level design record (schemas, invariants, algorithms, gotchas): `docs/FOOTHOLD_TECH_REFERENCE.md` (see its pivot notice for per-section applicability)
  - RAG pipeline (reduced scope: fuzzy course resolution): section 1
  - Pathway map and atlas layout (Mode C stretch only): section 2
  - Onboarding (Mode C stretch only): section 3
  - LLM engine, call log, SQLite kernel, app assembly, contracts conventions, testing seams: section 4
  - Recorded gotchas: the appendix
- The relevant schema contract in `docs/specs/` for any shape change.

Prefer the tech reference over browsing the Agentic-Calendar source.

## Development Rules

- Treat schemas in `docs/specs/` as contracts. Update specs before changing schema-related code.
- Keep LLM outputs structured. Prose explains decisions but is never the source of truth for validation, routing, or writes.
- Pass every parsed transcript through the course-resolution gate and every petition letter through the citation gate before serving; finding and violation codes are typed and fixture-tested.
- Preserve `run_id` and typed `reason_code` values across validation, service, and user-visible errors.
- Keep orchestration state explicit. Do not hide workflow state in prompts or LLM text.
- LLM SDK imports live only in `llm/`.
- Region packages do not import sibling regions; communicate through `contracts/` and `common/`.
- Keep re-implemented kernels minimal and purpose-built; do not carry over generality the reference code has and Foothold does not need.
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

Before writing any test, read `docs/TESTING_STRATEGY.md`.
It defines the suite's layer structure (static, unit/contract, integration seams, minimal E2E) and which layer a new test belongs in.

- `articulation_expr` evaluation has direct unit tests, including partial-series semantics and `note`/advisement leaves.
- Every evaluation reason code has a named fixture that proves the evaluator fires it; the petition citation validator has fixtures for invented courses and invented agreements.
- The repair loop is tested against FakeTransport: retry pacing, attempt sequences, cap exhaustion, boundary revalidation of schema-enforced output.
- Session middleware tests cover cookie minting and the client-user-id-overridden trust boundary.
- Frontend lib modules (`lib/evaluation.ts` view-model, `lib/courses.ts` chip state) are vitest-covered; view-model tests pin purity and order stability.
- Components have no tests; they must stay thin enough not to need them.
- Articulation build stages are testable on cached ASSIST JSON with zero network; the build report is reviewed after every full build.
- LLM-facing code is tested with fixtures, contracts, and pinned prompt hashes, never by trusting prompt wording.

## Deploy Verification Rules

- Target: Fly.io single machine; `articulation.db`/`corpus.db` baked read-only into the image; `sessions.db` on the `/data` volume; only secret is `ANTHROPIC_API_KEY`.
- A deploy is not done until the live URL passes a smoke check: `/healthz`, a full demo evaluation, and a petition generation.
- Green local tests are not evidence about production; verify against the live host.
- Pre-warm the demo evaluation and petition after every deploy; the demo video records against the live URL.

## Forbidden Shortcuts

- Do not let an LLM decide routing, validation outcomes, transferability, or confidence.
- Do not serve a transcript parse that has not passed the course-resolution gate, or a petition letter that has not passed the citation gate.
- Do not exceed 2 repair attempts per artifact.
- Do not treat invalid structured output as "good enough."
- Do not silently drop validation failures, retries, unresolved courses, or excluded agreements.
- Do not put an LLM in the retrieval path, the evaluator, or the arbitrage path.
- Do not log raw prompts or responses; hashes and counts only.
- Do not hand-edit committed generated artifacts; regenerate them.
- Do not copy code from Agentic-Calendar, ever.
- Do not add sign-in, a scheduler, a calendar, or degree-audit claims.
- Do not start Mode C (pathways) without an explicit user go-ahead.
