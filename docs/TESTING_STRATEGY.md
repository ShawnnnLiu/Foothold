# Testing Strategy

PIVOT NOTICE (2026-07-31): the product pivoted to the transfer credit navigator (see `FOOTHOLD_PATHFINDERS_PLAN.md`).
The layer structure and every principle below are unchanged; the product-specific examples map as follows:

- "prereq expression evaluation" -> `articulation_expr` evaluation (including partial-series and note semantics);
- "the pathway validator, one invalid fixture per violation code" -> the transfer evaluator's classification, one named fixture per typed reason code, plus the petition citation validator;
- "candidate pool projection" -> the `cc_courses` resolution vocabulary shared by autocomplete and the transcript validator;
- "the vocabulary gate" seam -> one `cc_courses` projection feeding both the transcript-resolution gate and the UI autocomplete; the petition findings object feeding both the prompt and the citation check;
- the repair-loop and HTTP-policy seams apply verbatim to the transcript parser and petition writer nodes.

This document defines how the Foothold test suite is shaped and where new tests belong.
It complements the Testing Requirements section of `CLAUDE.md`, which lists when tests are mandatory; this document explains at what layer to write them and why.

## Guiding Principle

We borrow the core idea of the testing trophy: invest where confidence per test is highest, and never mock internal seams.
We do not copy its proportions.
This codebase deliberately concentrates its value in pure deterministic kernels ("LLMs propose, deterministic infrastructure disposes"), so the unit/contract layer is legitimately the largest by test count.
The suite ends up pyramid-shaped by count but trophy-shaped by where the confidence comes from, and that is correct for this architecture.

The one-line rule when adding a test:

> Pure kernels get fixture-driven unit tests; axioms about seams get integration tests; nothing mocks a boundary that a fake transport or a temp SQLite file can make real.

## Layer 1: Static (already wired into `make check`)

`ruff`, `mypy --strict`, `schema-check --check`, and byte-identical regeneration checks run on every CI pass.
This layer does more work here than in a typical project: frozen Pydantic contracts with `extra="forbid"` catch shape drift between producer and consumer at typecheck/schema-check time, which eliminates a whole class of integration bugs before any test runs.

Planned addition: an import-boundary test asserting region packages do not import sibling regions.
That rule currently lives only in prose in `CLAUDE.md`; a cheap AST or import-graph check makes it enforced.

## Layer 2: Unit / Contract (largest by count)

Write fixture-driven unit tests, with zero mocks, for the pure deterministic kernels:

- prereq expression evaluation and satisfiability, including `note` leaves never being silently satisfied;
- the pathway validator, with one named invalid fixture per violation code proving each check fires;
- deterministic chunking;
- candidate pool projection;
- frontend layout purity, byte-stable snapshots, and order stability (in React-free `lib/` modules);
- every contract field constraint and model validator, each with a named invalid fixture.

These are pure functions over typed data.
Unit tests are cheapest and strongest exactly here, and a large count of them is not a trophy violation because none of them require mocking around implementation details.

## Layer 3: Integration (small in count, highest confidence value)

Integration tests exist because most of the non-negotiable axioms are properties of seams, and no unit test of either side can prove them.
The required integration seams are:

### The vocabulary gate

The candidate pool given to the proposer prompt IS the object the validator checks `unknown_course` against.
Unit tests of the pool builder and the validator can each pass while a re-derivation quietly diverges.
Wire pool, prompt cards, and validator through the real pathway service in one test to prove the single-projection invariant.

### The repair loop against FakeTransport

LLM node, validation failure, bounded repair (max 2 attempts), then the typed fallback path (`fallback_flat` for prereqs; drop the failing pathway and serve survivors) is a multi-module workflow.
FakeTransport substitutes at the transport seam only; everything inside the loop is real code.
Never mock the validator, the repair counter, or the fallback logic.

### The HTTP policy

200-with-`status: "failed"` vs 422 vs 409 depends on exception handler registration order (the `ValidationError` handler must be registered before the `ValueError` handler) and middleware wiring.
Registration-order bugs are invisible to unit tests by construction.
Test through FastAPI `TestClient` over the real app with a temp `sessions.db`.
The same suite covers the session cookie trust boundary (never trust a client-supplied user id) and the SPA catch-all mounting last.

### SQLite FTS5 retrieval

BM25 ranking and tokenizer behavior are properties of real SQLite, not of our code.
Never mock the database; run queries against a real index built from fixture data.

### The catalog build on cached HTML

Per-department fault isolation ("a failing department is excluded, never breaks the build") is a pipeline property.
Feed the build a fixture set with one poisoned department and assert the build completes with a typed `reason_code` for the exclusion.

## Layer 4: E2E (minimal)

One or two smoke tests through the API on a built catalog.
No frontend component tests: logic lives in unit-tested React-free `lib/` modules, and screens are thin renderers.
The contest demo-video walkthrough serves as the manual E2E pass.

## Hard Rules

- Deterministic assertions only; no live network, no live LLM calls, no wall-clock or PRNG dependence in tests.
- Prompt wording is never a test oracle; use fixtures, contracts, and pinned prompt hashes.
- Fakes are allowed only at external boundaries: the LLM transport (FakeTransport) and the network fetch layer (cached HTML fixtures).
- SQLite is never faked; use temp files or in-memory databases with the real schema.
- Every typed `reason_code` and violation code has at least one test that produces it.
