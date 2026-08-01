# Implementation Roadmap

This is the build-order plan for Astrolabe, derived from `STARMAP_PATHFINDERS_PLAN.md` (pivoted 2026-07-31 to the transfer credit navigator) and `STARMAP_TECH_REFERENCE.md`.
Those two documents remain the authority on product scope and mechanism design; this file only sequences the work into increments with exit criteria.
Date anchored: rewritten 2026-07-31; the contest window closes 2026-08-21.

## Pivot status

Increments 0-2 of the pre-pivot roadmap are DONE and survive the pivot unchanged: repo bootstrap, day-1 spikes (historical record in `docs/notes/day1_spikes.md`), and the common kernel + contracts machinery + first contracts (commit `8d29759`).
The pre-pivot increments 3-7 (bulletin fetch/parse, prereq extraction, CULPA ingest) are RETIRED.
Their execution docs 03, 05, and 07 in `docs/week-1-implementations/` were deleted on 2026-07-31 (recoverable in git history at commit 92998be); see that folder's README for per-doc status.
The implementation docs for the new increments 4-7 live in `docs/implementation-plans/articulation/`.

User-decided build order (2026-07-31): ASSIST corpus/pipeline first, then the deterministic transfer evaluator and Mode A end-to-end, then Mode B arbitrage, then Mode C pathways only if time remains (pre-cut by default).

## Sequencing thesis: the data spike still comes first

The one external unknown that can sink the pivot is ASSIST API access (keys, rate limits, terms).
Everything else in the plan is deterministic code over captured fixtures.
So the order is: spike ASSIST immediately, capture real agreement payloads as fixtures, shape the contracts from those fixtures, then build the pipeline and evaluator offline against cached JSON.
The LLM backbone moves to Week 2 because the build pipeline no longer has an LLM stage at all; the first consumer of the engine is the request-time transcript parser.

## Dependency spine

```
common kernel ✅ ──► contracts ✅ ──► assist spike ──► articulation contracts ──► fetch/normalize/store ──► evaluator ──► fuzzy matcher (FTS5)
                                                              │                                                  │
                                                              └───► llm engine + call log (Week 2) ──► transcript parser + petition writer ──► app/web ──► arbitrage ──► frontend
```

## Week 1 remainder (Jul 31 - Aug 6): articulation data is the product

### Increment 3: ASSIST spike (NETWORK: needs user go-ahead)

- Probe the documented API at `prod.assistng.org`: institution list, academic years, agreement list for the demo pair, one major agreement, one department agreement.
- Determine key requirements, rate behavior, and terms-of-use constraints; check what the assist.org frontend itself calls.
- Capture sample payloads verbatim into `backend/tests/fixtures/assist/` (they drive contract design and all offline tests).
- Record findings and the go/adapt/fallback decision in `docs/notes/assist_spike.md`.
- Start the curated cost table (`data/curated/costs.json`) with source URLs.

Exit: access confirmed and recorded; fixtures captured for both agreement categories; corridor scope confirmed or adjusted in the plan.

### Increment 4: articulation contracts

- Generalize `prereq_expr` into `articulation_expr` (same recursive all/any/course/note shape and validators; rename plus any ASSIST-specific leaf fields the fixtures demand).
- New contracts with specs in `docs/specs/`: `institution`, `agreement`, `articulation` (receiving side + sending expr + advisements), `cc_course`, `target_course`, `evaluation` (findings, buckets, typed reasons), reason-code additions (`advisement_note`, `partial_series`, `fuzzy_match`, `stale_year`, `no_articulation`, `still_owed`, `double_count_risk`, `unresolved`).
- Retire or repurpose the Columbia-shaped contracts (`course`, `offering`, `requirement_group`): delete their modules, specs, and fixtures in the same increment so `make check` stays honest.
- One invalid fixture per constraint, per the established harness.

Exit: contracts validate the captured ASSIST fixtures round-trip; schema `--check` green.

### Increment 5: fetch + normalize + store (NETWORK for the full corridor: needs user go-ahead)

- `assist/fetch.py`: polite 1 req/s fetcher over the corridor scope, URL-hash on-disk cache in `data/raw/`, per-agreement fault isolation.
- `assist/normalize.py`: nested/stringified payloads into validated contracts; template-cell and base articulation models; per-agreement try/except with typed exclusion reasons.
- `assist/store.py` + `scripts/build_articulation.py`: deterministic insert order, `VACUUM`, logical-dump `--check`; build report JSON in `data/reports/`.

Exit: `articulation.db` built for the corridor scope from cache; build report reviewed; SQL spot-checks pass on the demo pair.

### Increment 6: the deterministic transfer evaluator

- `transfer/evaluate.py`: pure functions from (course set, agreement set) to typed findings, per the plan's algorithm section: expression evaluation with satisfied/partial/unsatisfied, the classification buckets, units accounting, double-use flagging.
- `transfer/triage.py`: findings to the board view-model (stable ordering, units and dollar totals via the curated cost table).
- Fixture-driven tests: one named fixture per reason code and per edge case (partial series, note-only articulation, "no course articulated" cells, double-use).

Exit (Week 1 milestone, Aug 6): a curated demo student evaluates correctly at the CLI against the demo pair, hand-verified against the live assist.org agreement.

### Increment 7: fuzzy course matcher

- `retrieval/`: the FTS5/BM25 kernel at reduced scope (per-institution index over `cc_courses` code + title, quoted match compilation, deterministic tie-break, fail-fast if FTS5 missing).
- Fixed similarity threshold; below it, `unresolved`, above it without exact match, `fuzzy_match`.
- Build stage 4 wires `corpus.db`.

Exit: known misspellings and title-only entries resolve correctly in tests; threshold behavior pinned by fixtures.

## Week 2 (Aug 7 - 13): request loop

- LLM backbone exactly per tech reference 4.1/4.2 (engine, transports, call log, FakeTransport seam); unchanged by the pivot.
- `llm/transcript_parser.py` and `llm/petition_writer.py` nodes with their validators (course resolution gate; citation vocabulary gate), repair <= 2, typed fallbacks; FakeTransport tests first, live calls behind user go-ahead with `ANTHROPIC_API_KEY`.
- `transfer/arbitrage.py`: inverted articulation index, cost-ranked results (Mode B, deterministic).
- `app/web/`: FastAPI assembly in the pinned order, `sid` middleware, the plan's API surface, 200/422/409 policy, session store.
- Frontend skeleton (Vite + React + vitest): React-free `lib/evaluation.ts` and `lib/courses.ts`, screens wired end-to-end: pick, chips/paste, evaluate, triage board, petition drawer.

Milestone Aug 13: demo student to triage board + validated petition end-to-end; Mode B returns ranked savings via API.

## Week 3 (Aug 14 - 21): polish, ship, tell the story

- Triage board + petition drawer polish; evaluation theater; arbitrage tab; landing.
- Fly.io deploy by Aug 18; pre-warm the demo evaluation and petition.
- Video Aug 19-20; write-up Aug 20 (per the plan's skeleton); buffer Aug 21.
- Mode C pathways: only if all of the above is done by Aug 17 AND the user explicitly green-lights it; otherwise it stays cut.

## Standing decision points for the user

1. Increment 3: live network to ASSIST (the spike, then increment 5's full corridor fetch).
2. Increment 4: deleting the retired Columbia-shaped contracts and their fixtures.
3. Week 2: live Anthropic API calls (`ANTHROPIC_API_KEY`; register at stellic.com/pathfinders for credits first) and frontend scaffold dependencies (Vite, React, vitest).
4. Week 3: Fly.io account and deploy; any Mode C go-ahead.
5. Any new backend dependency beyond the already-approved set (pydantic, beautifulsoup4 may become droppable, anthropic; dev: pytest, ruff, mypy).

## AI tool disclosure ledger

Maintained from day one because omission is a disqualification ground: Claude Code (this agent), Claude API (transcript parser + petition writer nodes), plus anything added later.
