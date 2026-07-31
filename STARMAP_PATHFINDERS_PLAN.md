# Stellic Pathfinders: Columbia Course-Selection Helper ("Starmap")

This is an execution handoff plan.
The executing agent should build this as a NEW standalone repo, not inside Agentic-Calendar.
Agentic-Calendar (this repo) is a READ-ONLY design reference.
Do not copy any file contents from it; study the reference implementations and write new, smaller, purpose-built modules.
Reason: the official rules require the submission be newly created during the window (section 6.1), and the license grant (section 9.2) gives Stellic perpetual commercial rights to every element of the submission, so no Loop code may enter the submission repo.

## Context

Entry for the Stellic Pathfinders challenge (category: Degree Planning and Discovery).
The problem: course selection consumes expensive counselor manpower.
The product: students onboard with goals, completed courses, interests, and career direction; the system generates a few personalized pathways per major, each a set of course nodes with grounded fit reasoning, rendered as an interactive star-atlas map.
No scheduler, no calendar.
Data: Columbia College bulletin (~80 department pages with courses, prereq prose, term-offered info) + CULPA API (professor ratings, reviews, nuggets).

Contest facts (scraped from stellic.com/pathfinders on 2026-07-30):
- Window: built July 20 - Aug 21, 2026. Roughly 3 weeks remain.
- Deliverables: title/category, 500-word write-up, 2-min demo video, working prototype link, tools list.
- Judging (equal weights): real student problem, originality, scalability, design/UX, build quality.
- Rules: project must be "yours and new"; open-source libraries and public APIs are fine; AI tools encouraged; free Claude API credits at registration.
- Official terms reviewed 2026-07-30. Verdict: do NOT copy Loop code into the submission.
  Section 6.1 requires work "newly created during the Submission Period for purposes of this Competition" and bars pre-existing projects developed materially in advance; the open-source carve-out fails because Agentic-Calendar has no LICENSE file.
  Section 9.2 grants Stellic a perpetual, irrevocable, sublicensable, transferable license to commercialize "the Submission and any element thereof", so copied kernels would license Loop's core IP to Stellic forever.
  Section 6 makes AI-tool disclosure mandatory (list Claude Code, Claude API, and every AI tool used); omission is a disqualification ground under section 16.
- USER ACTION (not for the agent): register at stellic.com/pathfinders to get Claude credits.

## Locked decisions (user-confirmed)

1. New standalone repo built FROM SCRATCH during the contest window.
   Agentic-Calendar is a read-only design reference (patterns, architecture, invariants); zero file copying.
   Re-implemented kernels must be smaller and purpose-built (no snapshots-per-track, no prompt-version changelogs, no unused generality).
2. No sign-in: anonymous `sid` cookie sessions, server-side SQLite session store.
3. Scrape ALL Columbia College departments; hand-verify 3-5 demo majors (CS, Econ, + 2-3 for breadth such as Psych, English, Poli Sci).
4. Pathway generation: LLM proposes pathway candidates, deterministic validator disposes.
   The "LLMs propose, deterministic infrastructure disposes" architecture is the originality hook and the through-line for the write-up.

## Verified facts (de-risking done during planning)

- Bulletin dept pages use the CourseLeaf courseblock pattern (`.courseblock`, `.courseblocktitle`, `.courseblockdesc`, `.sc_courselist` for requirement tables).
- Prereq prose contains hyperlinked course codes (`<a href="/search/?P=COMS%20W3134">`), giving a deterministic ground-truth anchor for prereq extraction.
- Term info appears as `Fall 2026: COMS W1004` subheadings with instructor names (joinable to CULPA).
- Major-requirement tables live on the same dept pages.
- RISK: `api.culpa.info` failed DNS resolution during planning. CULPA is open source (github.com/culpaonline). Day-1 spike required; all CULPA fields optional; `--skip-culpa` build flag.

## Architecture

### Data model (`catalog.db`, build-time artifact, committed + baked into image)

- `departments`, `majors(curated flag)`, `courses(course_code PK, title, points, description, prereq_prose, prereq_expr_json, prereq_confidence, bulletin_url)`, `offerings(course_code, term, year, instructors)`, `requirement_groups(major_id, name, rule_json)`.
- CULPA tables: `culpa_professors(nugget, avg_rating)`, `culpa_reviews`, derived `course_ratings(course_code, avg_rating, review_count, top_review_excerpt, best_prof_name, best_prof_nugget)`.
- Course codes normalized as `"COMS W4701"`.
- Prereq expression: recursive JSON mirrored as a recursive Pydantic contract, with `all` / `any` groups and leaves `{course, equivalent_ok?}` or `{note}`.
  A `note` leaf is an unstructured escape hatch: never silently satisfied, always surfaced in the UI.
- Confidence tiers: `parsed` (LLM tree validated), `fallback_flat` (flat AND of hyperlinked codes after repair exhaustion), `none`.

Example prereq expression:

```json
{"all": [
  {"any": [{"course": "COMS W3134"}, {"course": "COMS W3136"}, {"course": "COMS W3137"}]},
  {"course": "COMS W3203", "equivalent_ok": true},
  {"note": "or instructor permission"}
]}
```

### Pipeline 1: catalog build (propose/dispose for prereqs, build-time)

`scripts/build_catalog.py`, stages idempotent, raw HTML cached to gitignored `data/raw/`:
1. fetch: dept index then ~80 dept pages, polite 1 req/s, on-disk cache keyed by URL hash.
2. parse: BeautifulSoup on CourseLeaf selectors; per-dept try/except; parse report JSON (`data/reports/parse_report.json`); failing depts get excluded from the majors list, never break the build.
3. prereq-extract: deterministic hyperlink code set first, then LLM proposes an expression tree, then a validator disposes (every course leaf must be in linked/catalog codes, every linked code accounted for in tree or a note, depth <= 3); repair <= 2 via the generation engine; exhaustion falls back to `fallback_flat`.
   This is the only LLM stage in the build; cost-tracked via the call log.
4. culpa: per-dept API ingest, join by course code where provided, else by (professor name intersect offering instructor names); `--skip-culpa` keeps the build green.
5. corpus: one CorpusDocument per course (title + description + prereq prose + fulfills notes) and one per requirement group into the corpus store; one snapshot; FTS5/BM25 only.
   Skip embeddings and hybrid fusion: BM25 over ~4k short docs is plenty and cuts a dependency plus an API key.

### Pipeline 2: pathway generation (propose/dispose, request-time)

Generate per-student at request time; personalization IS the product, so no per-major precomputation.
Cache by `sha256(major, sorted(completed), sorted(interests), normalized career text)`; pre-warm demo profiles after each deploy.

1. Deterministic candidate pool (`pathways/pool.py`): major dept + requirement-group + allied-dept courses, filtered to prereq-satisfiable within the planning horizon given completed courses, annotated with eligibility depth (now / after 1 semester / after 2).
2. Interest ranking: BM25 query built from interests + career free text over the corpus snapshot; take top ~60 candidates.
3. Prompt: compact structured "course cards" (code, title, points, terms offered, one-line prereq summary, CULPA score, 1-2 sentence description, requirement-group tags), NOT raw RAG chunks.
   Skip the source_claims layer entirely: the catalog is already structured verbatim-grounded data, and the UI drawer shows the underlying bulletin/CULPA text.
4. LLM proposes (frontier model, one call): 3 pathway candidates, each = name, 2-sentence thesis, 4 semesters of nodes `{course_code, semester_index, fit_reasoning, requirement_slot?}`.
5. Validator disposes (`pathways/validate.py`, pure functions) with typed violations: `unknown_course`, `duplicate_course`, `already_completed`, `prereq_unsatisfiable` (evaluate expr tree against completed union earlier-semester courses; note leaves are unsatisfiable-but-flagged; unknown term treated as any-term with an `assumed_term` flag), `term_infeasible`, `credit_load` (12-19 pts/semester default), `requirement_slot_invalid` (claimed course not in claimed group), `pathways_too_similar` (pairwise Jaccard > 0.6).
6. Repair <= 2 via the generation engine, feeding violation codes back; exhaustion drops the failing pathway (serve 2 of 3); only if all fail return a typed error ("try adjusting completed courses").
7. Persist the pathway set to the session store.

Swap: deterministic top-5 alternatives per node (same requirement group or same pool, re-validated server-side with the swap applied); no LLM in the swap path.
LLM backfill of fit reasoning for a swapped node is a cut-line item.

### Requirements scope

Lightweight requirements-aware, explicitly NOT a degree audit (degree audit is Stellic's core product).
Auto-parse `sc_courselist` best-effort everywhere; hand-curate `data/curated/requirements/{major}.json` for the demo majors; UI shows a "covers N of M core groups" badge per pathway.
Write-up framing: discovery upstream of audit ("we help students decide what to want; Stellic verifies it counts").

## Repo layout and reference mapping

All modules are written fresh; annotations name the Agentic-Calendar reference implementation to STUDY (never copy).

New repo `starmap/` (rename freely):

```
starmap/
  fly.toml                      <- new (ref: root fly.toml; 1-machine SQLite discipline)
  backend/
    Dockerfile                  <- new (ref: backend/Dockerfile)
    pyproject.toml
    src/starmap/
      common/                   <- new minimal kernel (ref: common/sqlite.py ensure_schema pattern,
                                   clock, ids, errors)
      contracts/                <- new Pydantic-v2 contracts (extra=forbid, frozen, invariant
                                   validators): course, prereq_expr, offering, requirement_group,
                                   culpa, student_profile, pathway, pathway_violation, reason_codes,
                                   corpus_document, retrieval_query/result
      retrieval/                <- new: minimal corpus store + deterministic chunking + FTS5/BM25
                                   (ref: retrieval/sqlite_registry.py, chunking.py, index.py;
                                   no snapshots-per-track, no vectors, no fusion)
      llm/
        engine.py               <- new: transport protocol + generation engine with schema
                                   validation, bounded repair <= 2, typed reason codes
                                   (ref: llm_nodes/anthropic_adapter.py _GenerationEngine)
        call_log.py             <- new token/cost log (ref: llm_nodes/call_log.py)
        prereq_extractor.py     <- new LLM node
        pathway_proposer.py     <- new LLM node
      catalog/                  <- new: fetch.py, parse_bulletin.py, parse_requirements.py,
                                   culpa.py, store.py, build.py
      prereqs/                  <- new: expr.py (eval/satisfiability), extract_validate.py
      pathways/                 <- new: pool.py, prompt_cards.py, validate.py, alternatives.py,
                                   cache.py, service.py
      app/web/                  <- new: app.py, config.py, deps.py,
                                   session.py (sid cookie middleware),
                                   routes_catalog.py, routes_pathways.py
                                   (ref: app/web/app.py SPA-mount pattern)
    tests/
  frontend/src/
    lib/atlas/                  <- new deterministic layout kernel: seeded force-directed or
                                   semester-column layout, React-free, byte-stable, unit-tested
                                   (ref: frontend/src/lib/atlas/layout.ts)
    lib/onboarding.ts           <- new React-free wizard-state module (ref: lib/intake.ts pattern)
    lib/pathway.ts              <- new: pathway view-model, swap state
    screens/                    Landing.tsx, Onboarding.tsx, Generation.tsx, Sky.tsx, NodeDrawer.tsx
    api/                        types.ts, client.ts
  data/
    curated/requirements/*.json
    catalog.db, corpus.db       <- committed build artifacts
  scripts/build_catalog.py
  docs/specs/*.schema.md        <- keep one-spec-per-contract discipline (write-up evidence)
```

Reference implementations in `/Users/shawnliu/Documents/Agentic-Calendar` (open with read access via `claude --add-dir`):
- `backend/src/agentic_calendar/llm_nodes/anthropic_adapter.py` (transport protocol, _GenerationEngine, repair loop, reason codes)
- `backend/src/agentic_calendar/retrieval/sqlite_registry.py`, `index.py`, `chunking.py`
- `backend/src/agentic_calendar/common/sqlite.py` (SqliteDatabase, ensure_schema)
- `frontend/src/lib/atlas/layout.ts` (byte-stable layout kernel)
- `frontend/src/lib/intake.ts` (wizard-state pattern)
- `fly.toml`, `backend/Dockerfile`

Time impact of from-scratch: budget roughly 2 extra days in Week 1 for the re-implemented kernels; recover it by keeping them minimal (the reference code carries generality Starmap does not need).

## API (session-scoped via HttpOnly SameSite=Lax `sid` cookie, lazily created by middleware)

- `GET /api/majors`
- `GET /api/courses?q=` (autocomplete)
- `GET /api/courses/{code}` (detail + CULPA)
- `POST /api/profile` (onboarding payload)
- `GET /api/me` (profile + latest pathway set)
- `POST /api/pathways` (generate; returns 202 + set_id, Generation screen polls `GET /api/pathways/{set_id}`)
- `POST /api/pathways/{set_id}/nodes/{node_id}/swap` with `{replacement_code}`
- `GET /healthz`

## Frontend (2-minute-demo surface set)

1. Landing: one screen, major picker + begin.
2. Onboarding: 4 steps behind React-free `lib/onboarding.ts`: (a) major + year, (b) completed courses via autocomplete chips, (c) interests chips + free text, (d) career direction.
3. Generation: staged progress theater ("scanning 4,000 courses... proposing pathways... validating prerequisites ✓").
   This screen IS the propose/dispose demo moment; show validator checks ticking.
4. Sky: atlas map; pathways as tabbed constellations; course nodes laid left-to-right by semester with prereq edges; completed courses as dim anchor stars.
5. NodeDrawer: fit reasoning, bulletin excerpt, CULPA rating + nugget badge + one review quote, terms offered, prereq status, alternatives list with one-click validated swap.

Cut from v1: side-by-side compare view (tabs suffice), mobile-specific sky, editing onboarding after generation (just restart).

## Deployment

Fly.io single machine.
`catalog.db` / `corpus.db` copied read-only into the image.
Mutable `sessions.db` (profiles, pathway sets, call log, cache) on the `/data` volume so demo links survive restarts.
Only secret: `ANTHROPIC_API_KEY`.

## Week-by-week milestones

Week 1 (Jul 30 - Aug 6): data is the product.
- Day 1: CULPA API spike (browser + culpaonline GitHub repo); pin bulletin selectors against 5 diverse depts (CS, Econ, English, Music, a language dept).
- Bootstrap repo from scratch; re-implement the minimal kernels (common, retrieval, llm engine) using the reference mapping above; CI with pytest + vitest.
- Fetch + parse all depts into catalog.db; review parse report.
- Prereq extraction pipeline end-to-end; hand-verify CS + Econ.
- Milestone Aug 6: `make build-data` green; SQL spot-queries correct for demo majors.

Week 2 (Aug 7 - 13): generation loop.
- Contracts for profile/pathway/violations; pool + prompt cards + proposer + validator + repair; requirement curation for demo majors; API + session store; cache.
- Ugly-but-real skeleton frontend wired end-to-end: onboarding -> generate -> pathway list.
- Milestone Aug 13: demo profile -> 3 validated pathways with grounded reasoning, < 45 s cold, instant cached.

Week 3 (Aug 14 - 21): sky, polish, ship.
- Atlas Sky + NodeDrawer + swap; Generation theater; visual polish.
- Deploy to Fly by Aug 18; pre-warm demo profiles.
- Record video Aug 19-20; write-up Aug 20; buffer Aug 21.

Cut-lines, first cut first:
1. LLM re-reasoning on swap (static "valid alternative" label instead).
2. Auto-parsed requirements for non-curated majors (badge only on curated).
3. CULPA review excerpts (keep numeric score).
4. Mobile sky.
5. Swap entirely.
6. Gate non-curated majors behind a "coverage varies" banner.

Never cut "all departments scraped": it is the headline scalability claim and scraping is cheap; only its quality claims are cuttable.

## Top risks

1. CULPA API dead or different (DNS failure observed 2026-07-30). Mitigation: day-1 spike, optional fields, `--skip-culpa`, graceful bulletin-only degradation.
2. Prereq prose defeats extraction (equivalents, instructor permission, cross-school codes). Mitigation: hyperlink anchors, note escape leaves, confidence tiers, flat-AND fallback, raw prose always shown in drawer.
3. Parse variance across ~80 dept pages. Mitigation: tolerant per-dept parsing, parse report, exclusion list; the curated tier carries the demo.
4. Request-time generation too slow or flaky for live judging. Mitigation: profile-hash cache, pre-warmed demo profiles, compact card prompts, drop-failing-pathway policy keeps 2 of 3 serving.
5. Solo scope creep on the sky UI. Mitigation: start with the boring semester-column layout (deterministic, trivial to implement), timebox any force-directed constellation upgrade to 3 days, keep the layout module React-free and unit-tested either way.

## Verification

- Build: `make build-data` produces catalog.db + corpus.db; review parse report; SQL spot-checks on demo majors (course counts, prereq trees for known chains like COMS W3134 -> W3157 / W4111).
- Backend tests: prereq expr evaluation and satisfiability, validator violation codes with invalid fixtures per code, repair-loop behavior against a fake transport, session middleware.
- Frontend tests: lib/atlas layout determinism, lib/onboarding state transitions, lib/pathway swap logic.
- E2E: run locally, onboard as a sophomore CS major with real completed courses, confirm 3 pathways render, hand-check every node's prereqs against the bulletin, swap round-trips, cached regeneration is instant.
- Deploy: Fly URL cold-start check, demo-profile pre-warm, record the video against the live URL.

## Kickoff (for the executing agent in a fresh session)

Setup (user runs once):

```bash
mkdir ~/Documents/starmap && cd ~/Documents/starmap && git init
claude --add-dir /Users/shawnliu/Documents/Agentic-Calendar
```

Kickoff prompt (copy-paste):

> Read /Users/shawnliu/Documents/Agentic-Calendar/STARMAP_PATHFINDERS_PLAN.md for full context, then read /Users/shawnliu/Documents/Agentic-Calendar/STARMAP_TECH_REFERENCE.md - it contains the recorded design details (schemas, invariants, algorithms, gotchas) for re-implementing the RAG pipeline, pathway map, and onboarding, so prefer it over browsing the Agentic-Calendar source.
> Build the project in this repo (starmap), from scratch.
> Agentic-Calendar is mounted read-only as a design reference: study the reference files named in the plan's repo-layout section, but NEVER copy file contents from it - every line in this repo must be newly written (contest rule, sections 6.1 and 9.2 of the official terms).
> Execute Week 1: day-1 CULPA API spike, bulletin selector pinning against 5 diverse departments, repo bootstrap with minimal re-implemented kernels (common, retrieval with FTS5/BM25 only, llm engine with bounded repair, call log), then the full catalog build pipeline with the prereq propose/dispose extraction.
> Write a short CLAUDE.md for this repo first (from-scratch rule, propose/dispose thesis, no calendar/scheduler scope).
> Follow the plan's cut-lines and risk mitigations.
> Commit at the end of every increment.
> Do not modify the Agentic-Calendar repo.
