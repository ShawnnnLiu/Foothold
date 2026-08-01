# Stellic Pathfinders: Astrolabe, the Transfer Credit Navigator

PIVOT NOTICE (2026-07-31): this plan supersedes the Columbia course-selection helper ("Starmap") plan.
The pre-pivot plan is preserved in git history (last pre-pivot version at commit `8d29759`, this same file path).
The pathway/course-discovery feature is demoted to the lowest-priority stretch tier; it ships only if everything else lands early, and it can be cut entirely.
The filename is kept so references in `CLAUDE.md`, `AGENTS.md`, and the week-1 docs stay valid.

## Context

Entry for the Stellic Pathfinders challenge, category: **Overcoming Obstacles** (cost, paperwork, friction).
Changed from Degree Planning and Discovery: that category will be flooded with AI course advisors, and the transfer problem carries a far stronger evidence base.

The problem: transfer students lose credits, money, and time.
The 2017 GAO report (GAO-17-574) estimates students who transferred lost on average 43 percent of their credits; roughly 35 percent of students transfer at least once; half of transfers are Pell recipients, so lost credits are lost aid dollars.

The product: **Astrolabe**, a transfer credit navigator for the largest transfer corridor in the US, California community colleges to UC/CSU.

- Mode A, Transfer Check (the headline): student picks their community college, target university, and major, then enters their courses (paste, autocomplete chips, or transcript upload); Astrolabe evaluates their courses against the official ASSIST articulation agreement and renders a triage board: transfers cleanly / at risk / no articulation, plus the major requirements still owed, with units and dollar figures.
  The demo climax: a grounded draft petition letter for at-risk and lost credits, citing the specific articulation agreement.
- Mode B, Gen-Ed Arbitrage (second priority): an enrolled UC/CSU student asks "what can I take at a community college that articulates back to my degree?"; Astrolabe inverts the same articulation index and ranks options by cost saved (CC per-unit cost vs university per-unit cost).
- Mode C, Transfer Pathways (stretch, pre-cut): "you have not transferred yet; here is what to take at your CC next term to maximize articulated credit toward your target major."
  This reuses the pre-pivot pathway proposer/validator framework and is the ONLY tier where that framework survives.

It is not:

- a degree audit (that is Stellic's core product; we sit upstream and pre-enrollment: the student has not even applied yet);
- an advising chatbot;
- a system where LLM prose controls workflow state or decides transferability.

Core thesis, sharpened by the pivot:

> LLMs propose. Deterministic infrastructure disposes.
> The AI never decides what transfers; the articulation agreement does.

The build pipeline is now fully deterministic (ASSIST serves structured JSON; there is no build-time LLM stage at all).
The two LLM nodes are both request-time edges: messy human input in (transcript parsing), grounded human output out (petition letter).
Everything between them, the transfer verdict itself, is deterministic evaluation over checked-in articulation data.

## Contest facts (re-verified against stellic.com/pathfinders on 2026-07-31)

- Window: built Jul 20 - Aug 21, 2026. Three weeks remain from the pivot date.
- Deliverables: title/category, 500-word write-up, 2-min demo video (YouTube/Vimeo/Loom), working link, complete tool inventory.
- Judging, five equal weights: real student problem, originality, scalability and student impact, design/UX, build quality.
- "Coders not required; non-technical judges consider helpfulness above technical complexity."
- One person may enter up to three submissions (wins only the highest prize).
- AI tool disclosure is mandatory; omission is a disqualification ground.
- USER ACTION (not for the agent): registration at stellic.com/pathfinders provides Claude API credits.

## Competitive landscape (researched 2026-07-31)

Transferology (CollegeSource), TES, and ASSIST.org itself all exist and are large.
All three are lookup tables that assume the student already knows what to search.
None of them does: transcript in, full articulation mapping out, risk triage, petition letter.
The write-up MUST name Transferology and state this differentiation explicitly, or a judge who knows the space will dock originality.

## Locked decisions (user-confirmed 2026-07-31)

1. Pivot confirmed: transfer credit navigator is the product; category is Overcoming Obstacles.
2. Build order: ASSIST corpus/pipeline first, then the deterministic transfer evaluator and Mode A end-to-end, then Mode B arbitrage, then (only if time remains) Mode C pathways.
3. The pathway framework is the lowest priority and may be cut without replacement.
4. The credit transfer evaluation algorithm is deterministic; no LLM participates in the transfer verdict.
5. Exactly two LLM nodes, both request-time: the transcript parser and the petition writer.
   There is no build-time LLM stage.
6. Everything else from the pre-pivot charter stands: from-scratch rule, no sign-in `sid` sessions, committed build artifacts, bounded repair, typed reason codes, polite fetching.

## Verified facts and open spikes

Verified during pivot research (2026-07-31):

- ASSIST has a documented JSON API at `prod.assistng.org/apidocs` (agreements, major articulations by course, department articulations by course, institution and academic-year lists).
- Example endpoint shape: `GET /articulation/api/Agreements/Published/for/{receivingId}/to/{sendingId}/in/{yearId}?types=Department`.
- Agreement payloads embed articulations as a JSON string of an array; Department/Prefix agreements use a base articulation model, Major/GE agreements use a template-cell model.
- Some endpoints mention API keys; a community reverse-engineering writeup (rombutan.com) and open-source consumers (e.g. `oshaw/assist-flowchart`) indicate the site's own endpoints are publicly reachable.
- An official "Data Extract & API Specifications" PDF exists (resource.assist.org); data questions route to help@assist.org.

Open spikes (day 1 of the pivot, mirrors the retired CULPA spike discipline):

1. ASSIST access: which endpoints need keys, what the site's own frontend calls, rate behavior, terms-of-use constraints on caching; record findings in `docs/notes/assist_spike.md`.
2. Payload shapes: capture full sample agreement JSONs (major and department types) for the demo pair into `backend/tests/fixtures/assist/` and study the template-cell model before writing contracts.
3. Cost data for Mode B: confirm current CA CC per-unit cost and per-unit figures for the pinned targets; curate into `data/curated/costs.json` with source URLs (no invented numbers).

## Corridor scope

Sending side: all California community colleges (~116), the headline scalability claim.
Receiving side: a pinned target list of 4 institutions (proposed: UC San Diego, UCLA, UC Irvine, San Jose State; adjust after the spike).
Major depth: a pinned major set (proposed: Computer Science, Economics, Psychology, Biology, Business) fetched for every (CC, target) pair; ALL majors fetched for the hand-verified demo pairs.
Proposed demo pair: De Anza College to UC San Diego, Computer Science.

Fetch-volume sanity: agreements are fetched per (sending, receiving, year, major-or-department); 116 CCs x 4 targets x ~5 majors is roughly 2,300 requests, about 40 minutes at the polite 1 req/s, cached on disk after the first run.
Never cut "all sending CCs": scraping is cheap and it is the scalability headline; only its depth claims (majors per pair) are cuttable.

## Architecture

### Data model (`articulation.db`, build-time artifact, committed + baked into image)

- `institutions(id, assist_id, name, kind)` with `kind` in `cc | uc | csu`.
- `academic_years(id, assist_id, label)`; evaluation always uses the latest published year, with the year recorded on every finding.
- `agreements(id, sending_id, receiving_id, year_id, category, label, assist_key)` with `category` in `major | department | ge`.
- `articulations(id, agreement_id, position, receiving_side_json, sending_expr_json, advisements_json)`.
- `cc_courses(institution_id, course_code, title, units_min, units_max)` extracted from sending cells (feeds autocomplete, transcript validation, and the FTS index).
- `target_courses(institution_id, course_code, title, units)` extracted from receiving cells.
- Curated: `data/curated/costs.json` (per-unit costs with source URLs); `data/curated/demo_students/*.json` (fixture transcripts for pre-warm and the video).

The sending-side expression is a recursive tree with `all` / `any` groups and leaves `{course}` or `{note}`, the same shape as the pre-pivot `prereq_expr` contract (already built and fixture-tested); it is generalized into an `articulation_expr` contract rather than re-invented.
A `note` leaf (ASSIST advisements, "must complete entire series", "no credit if taken after...") is never silently satisfied: it downgrades a match to at-risk and is always surfaced in the UI.

Example sending-side expression ("MATH 1A and MATH 1B, or the honors series"):

```json
{"any": [
  {"all": [{"course": "MATH 1A"}, {"course": "MATH 1B"}]},
  {"all": [{"course": "MATH 1AH"}, {"course": "MATH 1BH"}, {"note": "honors series must be completed entirely"}]}
]}
```

### Pipeline 1: articulation build (fully deterministic, no LLM)

`scripts/build_articulation.py`, stages idempotent, raw JSON cached to gitignored `data/raw/`:

1. fetch: institutions and years, then agreement lists and agreement payloads for the corridor scope; polite 1 req/s, on-disk cache keyed by URL hash, per-agreement fault isolation.
2. normalize: parse the nested/stringified articulation JSON into validated contracts; per-agreement try/except; build report JSON (`data/reports/build_report.json`) with per-pair status; a failing agreement is excluded and reported, never breaks the build.
3. store: write `articulation.db` in deterministic insert order; `VACUUM`; logical-dump `--check` mode as already established for committed artifacts.
4. corpus: FTS5/BM25 index over `cc_courses` (code + title, per institution) into `corpus.db` for fuzzy transcript-course resolution; deterministic, no embeddings.

### The transfer evaluation algorithm (deterministic, `transfer/`)

Input: a validated student course set for one sending CC, a target institution, a major, the latest agreement year.

1. Load the major agreement (plus department/GE agreements where fetched) for the pair.
2. For each articulation, evaluate the sending-side `articulation_expr` against the student's course set: satisfied, partial (some leaves of an `all` group present, e.g. half a series), or unsatisfied.
3. Classify with typed reason codes:
   - `transfers_clean`: expression fully satisfied, no note leaves involved.
   - `at_risk` with a sub-reason: `advisement_note` (a note leaf is present), `partial_series` (partial `all` group), `fuzzy_match` (a course resolved by title similarity rather than exact code), `stale_year` (agreement year older than latest).
   - `no_articulation`: a student course that appears on no satisfied or partial articulation sending side.
   - `still_owed`: receiving-side requirements in the major agreement with no satisfied articulation.
4. Units accounting: sum units per bucket; join `costs.json` to express the at-risk and lost buckets in dollars.
5. Double-use flagging: a student course consumed by more than one satisfied articulation is allowed but flagged `double_count_risk` when any involved advisement restricts it.

Every finding carries the agreement key, articulation position, and year, so the UI and the petition letter can cite ground truth.
No silent drops: unresolved input courses and excluded agreements surface as typed findings, never disappear.

### Pipeline 2: the two request-time LLM nodes (propose/dispose)

Node 1, transcript parser (`llm/transcript_parser.py`):

- LLM proposes a structured course list `{course_code, title, units, term?}` from pasted transcript text (or extracted PDF text).
- The validator disposes: every proposed course must resolve against that CC's `cc_courses` (exact code match, else FTS5 fuzzy title match above a fixed threshold, flagged `fuzzy_match`, else typed `unresolved`).
  The `cc_courses` projection given to the resolver IS the vocabulary the UI autocomplete uses: one projection, two consumers, never a re-derivation (the vocabulary-gate axiom, relocated).
- Repair <= 2 with violation feedback; exhaustion falls back to the deterministic path: the user fixes unresolved chips by hand.
  The chip/autocomplete input path is fully deterministic and is the primary demo path; transcript upload is the wow-path.

Node 2, petition writer (`llm/petition_writer.py`):

- Input: the deterministic findings object only (at-risk and lost items with their citations), never raw articulation prose.
- LLM proposes a petition letter draft.
- The validator disposes: every course code and agreement citation appearing in the letter must exist in the findings object (extracted by pattern, checked against the findings vocabulary); no invented policies or courses survive.
- Repair <= 2; exhaustion falls back to a deterministic template letter with slots filled from the findings.

Both nodes run through the bounded-repair generation engine and call log already specced (tech reference 4.1, 4.2), pinned to `claude-sonnet-5`.

### Mode B: gen-ed arbitrage (deterministic, `transfer/arbitrage.py`)

Invert the articulation index: receiving course or GE area -> CC courses that articulate to it.
Input: target institution plus the requirements or courses the student still needs (picked from `target_courses`, or carried over from a Mode A evaluation's `still_owed` list).
Output: articulating CC options ranked by `units x (target_per_unit_cost - cc_per_unit_cost)`, each citing its agreement.
No LLM anywhere in Mode B.

### Mode C: transfer pathways (stretch tier, pre-cut)

The pre-pivot pathway framework (candidate pool, prompt cards, proposer node, validator, swap) retargets to: propose next-term CC course plans that maximize articulated units toward the target major.
Nothing in Modes A/B may depend on Mode C code.
If built, it adds a third LLM node and its own plan revision first; do not start it without an explicit user go-ahead.

## What survives from the pre-pivot build

Already built and kept as-is: repo bootstrap, Makefile/CI, `common/` kernel (sqlite, dbdump, clock, ids, errors), contracts machinery (frozen `extra="forbid"` base, dedup helpers, invalid-fixture harness, schema generation with `--check`).
Kept with generalization: `prereq_expr` becomes `articulation_expr` (same recursive all/any/course/note shape, same evaluator semantics, same fixtures pattern).
Kept as specs to implement unchanged: the LLM generation engine and call log (tech reference 4.1, 4.2), FTS5/BM25 retrieval (reduced scope: course-title fuzzy match only), the FastAPI/session patterns.
Retired: bulletin fetch/parse (CourseLeaf), CULPA ingest, offerings/terms, requirement-group curation, the sky/atlas layout kernel (unless Mode C revives a simplified board layout).
The retired day-1 spike findings (`docs/notes/day1_spikes.md`) stay as a historical record of the spike discipline.

## API (session-scoped via HttpOnly SameSite=Lax `sid` cookie, unchanged)

- `GET /api/institutions?kind=cc|target`
- `GET /api/targets/{id}/majors`
- `GET /api/cc/{id}/courses?q=` (autocomplete over `cc_courses`)
- `POST /api/transcript/parse` (LLM node 1; 202 + id, poll `GET /api/transcript/{id}`)
- `POST /api/evaluations` (deterministic Mode A; synchronous)
- `GET /api/evaluations/{id}`
- `POST /api/evaluations/{id}/petition` (LLM node 2; 202 + id, poll)
- `GET /api/arbitrage?target=&needs=` (deterministic Mode B)
- `GET /healthz`

HTTP policy unchanged: LLM failure after repair exhaustion is 200 with `status: "failed"` and a typed `reason_code`; contract-invalid requests 422; precondition failures 409; HTML `no-cache`; SPA catch-all last.

## Frontend (2-minute-demo surface set)

1. Landing: "Don't lose the credits you already earned." CC picker, target picker, major picker.
2. Courses: autocomplete chips (primary), paste-transcript box (LLM path), sample-transcript button (demo insurance).
3. Evaluation theater: deterministic checks ticking ("resolved 24 of 25 courses... evaluated 61 articulations... checked 12 advisements").
   This screen IS the propose/dispose demo moment.
4. Triage board: three columns, green (transfers cleanly, N units), amber (at risk, each with its typed reason and citation), red (no articulation); a still-owed panel; units and dollar totals in the header.
5. Petition drawer: select at-risk/lost items, generate the grounded draft letter, copy button, citations visible.
6. Arbitrage tab (Mode B): "save $X" ranked list with agreement citations.

All logic in React-free unit-tested `lib/` modules (`lib/evaluation.ts` view-model, `lib/courses.ts` chip state); screens are thin renderers; no component tests.
Cut from v1: PDF upload (paste only), multi-CC transcripts, editing inputs after evaluation (restart), any atlas/sky visualization.

## Deployment

Unchanged: Fly.io single machine; `articulation.db` / `corpus.db` read-only in the image; mutable `sessions.db` on the `/data` volume; only secret `ANTHROPIC_API_KEY`; pre-warm the demo evaluation and petition after each deploy.

## Week-by-week milestones

Week 1 remainder (Jul 31 - Aug 6): the articulation data is the product.

- Day 1: ASSIST spike (access, terms, sample payloads captured as fixtures); cost-data curation started.
- Contracts: `articulation_expr` (generalized from `prereq_expr`), `institution`, `agreement`, `articulation`, `cc_course`, `evaluation` findings, reason-code updates; specs and fixtures first.
- Fetch + normalize + store pipeline over the corridor scope; build report reviewed.
- The deterministic evaluator with hand-verified results for the demo pair against the live ASSIST site.
- Milestone Aug 6: `make build-data` green; a fixture student evaluates correctly end-to-end at the CLI, verified by hand against assist.org.

Week 2 (Aug 7 - 13): request loop.

- LLM backbone (engine + call log, spec unchanged), transcript parser node, petition writer node, against FakeTransport first, then live behind the user's go-ahead.
- FastAPI app, session middleware, the API surface above; FTS5 fuzzy matcher; Mode B arbitrage engine.
- Ugly-but-real frontend wired end-to-end: pick, enter courses, evaluate, triage board, petition.
- Milestone Aug 13: demo student to triage board + validated petition letter, < 30 s cold for the LLM paths, instant for evaluation; Mode B returns ranked savings.

Week 3 (Aug 14 - 21): polish, ship, tell the story.

- Triage board and petition drawer polish; evaluation theater; landing.
- Deploy to Fly by Aug 18; pre-warm demo profiles.
- Video Aug 19-20 (open on the GAO 43 percent stat, close on the petition letter); write-up Aug 20 (name Transferology, state the differentiation, disclose all AI tools); buffer Aug 21.
- Mode C pathways: only if everything above is done by Aug 17, and only after an explicit user go-ahead.

Cut-lines, first cut first:

1. Mode C pathways (pre-cut by default).
2. Transcript paste/parse node (chips-only input; the evaluator and petition still demo fully).
3. Mode B arbitrage UI (keep the API + one screenshot for the write-up).
4. GE/department agreements (major agreements only).
5. Non-demo targets (shrink the pinned target list, never the sending-CC list).

## Top risks

1. ASSIST API access or terms block programmatic fetch (keys, rate limits, prohibitive ToU).
   Mitigation: day-1 spike before any pipeline code; the official data-extract PDF and help@assist.org as the fallback channel; worst case, pin the demo corridor from manually exported agreement reports.
2. Template-cell payload complexity defeats clean normalization (major/GE agreements embed a more complex cell model than department ones).
   Mitigation: fixtures captured in the spike drive contract design; per-agreement fault isolation and the build report; department-type agreements as the fallback shape.
3. Transcript parse variance.
   Mitigation: chips/autocomplete is the primary deterministic path; paste-parse is bounded-repair with typed `unresolved` fallback; the demo uses a curated sample transcript.
4. Degree-audit collision in judging (Stellic builds transfer evaluation for institutions).
   Mitigation: framing discipline everywhere: pre-transfer, pre-application, student-side; "we help students protect credits before they apply; Stellic verifies them after they enroll."
5. Petition letter safety (an appeal citing wrong policy harms the student).
   Mitigation: the citation vocabulary gate (letter may only cite findings), the deterministic template fallback, and an on-screen "verify with your counselor" disclaimer.
6. Time: three weeks with a mid-window pivot.
   Mitigation: the kernel and contracts machinery are already built and green; the build pipeline has no LLM stage; cut-lines are pre-ordered and Mode C is pre-cut.

## Verification

- Build: `make build-data` produces `articulation.db` + `corpus.db`; build report reviewed; SQL spot-checks on the demo pair (agreement counts, known articulations such as the De Anza CIS series to UCSD CSE lower-division mappings, checked by hand against assist.org).
- Backend tests: `articulation_expr` evaluation including partial-series and note semantics; evaluator classification with one named invalid/edge fixture per reason code; petition citation validator; repair loop against FakeTransport; session middleware trust boundary; HTTP policy through TestClient.
- Frontend tests: `lib/evaluation.ts` view-model determinism and order stability; chip-state transitions.
- E2E: run locally, evaluate the curated demo student, hand-check every finding against the live ASSIST agreement, generate the petition, confirm every citation resolves; Mode B savings ranked correctly against the curated cost table.
- Deploy: Fly URL cold-start check, pre-warm, record the video against the live URL.

## Write-up skeleton (500 words, drafted Aug 20)

1. The stat: 43 percent of credits lost (GAO-17-574); half of transfer students are Pell recipients.
2. The product: transcript in, triage out, petition letter in hand; gen-ed arbitrage flips the same engine into money saved.
3. The differentiation: Transferology/TES/ASSIST are lookup tables; Astrolabe is transcript-in, letter-out.
4. The architecture: the AI never decides what transfers; the articulation agreement does; LLMs only translate messy human input in and grounded human output out, with bounded repair and typed fallbacks.
5. Scalability: every CA community college on day one; an equivalency-table adapter per state is the expansion unit.
6. Full AI-tool disclosure: Claude Code, Claude API (two request-time nodes), and anything added.
