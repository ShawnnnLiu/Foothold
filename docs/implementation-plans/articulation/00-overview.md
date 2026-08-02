# Articulation Increments: Overview

This folder turns increments 4-7 of `docs/IMPLEMENTATION_ROADMAP.md` (the pivoted Astrolabe roadmap) into executable implementation plans.
One doc per increment, written for a less-capable executor model per `AGENTS.md` "Implementation Plan Conventions": every design decision is locked here; the executor implements and does not design.
Authored 2026-07-31; all cited symbols, file paths, and fixture facts verified against `main` at commit `4762feb` on that date.

Authority order for an executing session: user chat instructions, `CLAUDE.md`, `AGENTS.md`, `docs/STARMAP_PATHFINDERS_PLAN.md` + `docs/STARMAP_TECH_REFERENCE.md`, these docs, `docs/specs/`, code.
Citations like "TR 4.5" mean `docs/STARMAP_TECH_REFERENCE.md` section 4.5 and are binding pointers, not optional background.
Citations like "spike doc" mean `docs/notes/assist_spike.md`, the verified ground truth for ASSIST API mechanics and payload shapes.

## Scope and dependency order

| Doc | Roadmap increment | Depends on |
|---|---|---|
| `01-articulation-contracts.md` | 4: articulation contracts + retirement of the Columbia-shaped contracts | done increments 0-3 |
| `02-assist-fetch-normalize-store.md` | 5: ASSIST fetch, normalize, store, build report | 01 |
| `03-transfer-evaluator.md` | 6: deterministic evaluator, triage view-model | 01, 02 |
| `04-fuzzy-course-matcher.md` | 7: per-institution FTS5/BM25 fuzzy course matcher | 01, 02 |
| `SPLITS.md` | session splits with kickoff prompts and gates | all |

Increment 3 (the ASSIST spike) is DONE; its findings live in the spike doc and its captured payloads in `backend/tests/fixtures/assist/`.
Those seven fixture files are the design source for every schema decision below; do not design from memory of ASSIST.

## The seven captured fixtures (design inputs, never edited)

| File | What it pins |
|---|---|
| `academic_years.json` | `{id, fallYear}` list; id 76 = 2025-2026, the latest published year. |
| `institutions.json` | 181 institutions; 116 with `isCommunityCollege: true`; `category` values 0 (CSU), 1 (UC), 2 (CCC), 5 (private/independent); `code` is space-padded (e.g. `"UCSD    "`); `names[]` entries carry optional `fromYear`. |
| `categories_113_to_7_y76.json` | Category codes `major`, `dept`, `prefix`, `breadth` with per-pair `hasReports`. |
| `agreement_reports_major_113_to_7_y76.json` | 168 major reports; key format `76/113/to/7/Major/<guid>`. |
| `agreement_reports_dept_113_to_7_y76.json` | 86 dept reports; key format `76/113/to/7/Department/<int>`. |
| `agreement_major_cse_cs_113_to_7_y76.json` | Template-cell model; 8 articulations; `templateAssets` with `RequirementGroup`/`GeneralTitle`/`GeneralText`; an `Or`-instruction group (CSE 15L or CSE 29) whose cells have NO articulation entries. |
| `agreement_dept_math_113_to_7_y76.json` | Base model (bare articulation list); `templateAssets` null; MATH 10B/10C carry `sendingArticulation: null` ("No Course Articulated"). |

Two payload facts the spike doc's prose does not spell out, verified 2026-07-31 and binding on normalization:

- "No Course Articulated" appears BOTH as `sendingArticulation: null` (dept fixture, MATH 10B/10C) and as empty `items` (spike doc, major-model observation); both mean the same thing.
- Template-asset cells join to articulations via the cell's `id` field equaling the articulation entry's `templateCellId`; cells with no matching articulation entry exist (CSE 15L, CSE 29) and mean "no articulation published for this cell".

## Globally locked decisions

These bind every increment and are not to be relitigated by executors.

### Toolchain, layout, dependencies

- Everything from `docs/week-1-implementations/README.md` "Globally locked decisions" still binds except where it names retired Columbia-specific stages.
- NO new dependencies anywhere in increments 4-7: HTTP via stdlib `urllib.request` + `http.cookiejar`, fuzzy similarity via stdlib `difflib`.
  `beautifulsoup4` became unused with the Columbia bulletin pipeline and was REMOVED on 2026-08-01 with the user's go-ahead, along with its `types-beautifulsoup4` stub; the runtime dependency set is now `pydantic` and `anthropic` only.
- Data artifacts: `data/articulation.db` and `data/corpus.db` (committed, read-only at runtime), raw fetch cache in gitignored `data/raw/assist/`, build report in committed `data/reports/`, curated inputs in `data/curated/`.
- Package moves per the plan's architecture section: increment 5 creates `assist/` and deletes the empty pre-pivot `catalog/` package; increment 6 creates `transfer/` and deletes the empty pre-pivot `prereqs/` package.

### Course-code normalization (replaces the Columbia regex)

`contracts/codes.py` is rewritten in increment 4; the Columbia `^[A-Z]{2,4} [A-Z]{1,2}[0-9]{4}$` regex is replaced by:

```python
COURSE_CODE_RE = re.compile(
    r"^[A-Z][A-Z&/.\-]{0,9}(?: [A-Z][A-Z&/.\-]{0,9}){0,2} [A-Z]{0,2}[0-9]{1,4}[A-Z]{0,3}$"
)
```

- Shape: one to three prefix tokens (letters plus `&/.-`), then one number token (up to 2 leading letters, 1-4 digits, up to 3 trailing letters).
- Covers every code in the captures: `MATH 1A`, `MATH 2AH`, `STAT C1000H`, `CIS 22C`, `CIS 22CH`, `CSE 15L`, `MATH 20E`, `CSE 11`.
- `normalize_course_code(raw)` keeps its current contract: uppercase, collapse internal whitespace runs to one space, strip, then fullmatch; `ValueError` naming the input on failure.
- New helper in the same module: `course_code_from_parts(prefix: str, number: str) -> str` returning `normalize_course_code(f"{prefix} {number}")`; this is the single derivation every contract and normalizer uses.
- A code that fails normalization at build time is a per-articulation typed exclusion (`course_code_unparseable`), counted in the build report, never fatal (fault-isolation axiom).

### Reason-code families (one-time pivot exception to append-only)

The append-only-forever rule in `docs/specs/reason_codes.schema.md` exists so persisted or logged codes never dangle.
`PrereqExtractionCode`, `BuildCode`, and `CorpusCode` never shipped a producer and no artifact or log row carries their values; their consumers are retired by the pivot before ever existing.
Locked: increment 4 DELETES those three families under the same 2026-07-31 pivot approval that retires the Columbia-shaped contracts, and records this paragraph's rationale in the spec as a one-time exception.
`LlmReasonCode` is unchanged (its consumer, the Week 2 LLM backbone, is alive).
Increment 4 ADDS three families (exact members locked in doc 01): `EvaluationFindingCode`, `AssistBuildCode`, `RetrievalCode`, plus the `TriageBucket` enum and the `BUCKET_FOR_CODE` mapping.

### Advisements are fixture-pending (never invent shapes)

Per the spike doc, `attributes` lists exist at four levels (articulation, sending-articulation, group, course) and are the advisement carrier, but every captured list is EMPTY.
Locked treatment, restated in docs 01-03:

- The note-leaf MECHANISM (contract shape, evaluator semantics) is built and tested now with synthetic note fixtures.
- The attributes-to-text MAPPING is deferred: `assist/normalize.py` ships `advisement_texts(attributes)` that returns `[]` for an empty list and raises the typed `advisement_shape_unknown` exclusion for anything non-empty.
- The first corridor fetch (split S9c) captures one advisement-bearing agreement payload as a new fixture in `backend/tests/fixtures/assist/`, pins the real shape in `advisement_texts`, adds its tests, and rebuilds; the build report's `advisement_shape_unknown` count is the signal that drives this.
- Nothing anywhere silently satisfies, drops, or paraphrases an advisement (axiom).

### Committed-artifact identity at ASSIST scale

`articulation.db` and `corpus.db` follow the canonical-logical-dump identity from `docs/week-1-implementations/README.md` ("Committed-artifact identity") via `common/dbdump.canonical_dump`.
Deviation, locked here: the raw ASSIST cache (`data/raw/assist/`) is gitignored and too large to commit, so CI cannot regenerate the full corridor.
Therefore `make build-check` (regenerate from local cache, compare dumps) is a LOCAL gate run before any commit that touches the artifacts, and CI's `make check` enforces determinism through fixture-driven tests instead (store the demo-pair fixtures twice, assert identical dumps).
Both gates are specified in doc 02.

### Out of scope for increments 4-7 (do not build)

- No LLM code of any kind; the LLM backbone is Week 2 (`docs/week-1-implementations/04-llm-backbone.md` still applies as written).
- No FastAPI, sessions, or frontend.
- No Mode B arbitrage and no Mode C pathways.
- `prefix` and `breadth` agreement categories are not fetched or modeled (`category` is a closed `major | dept` set; widening it later is an append).
- `contracts/corpus_document.py` and its spec, fixtures, schema, and tests stay untouched: it is dormant after the pivot but its deletion is NOT covered by the 2026-07-31 approval (standing decision point below).

## Permission gates

| Gate | Split | What to ask the user |
|---|---|---|
| Live network: full corridor fetch (~2,300 requests, ~40 min at 1 req/s) | S9c | Go-ahead before the first request; also confirms ASSIST attribution text |
| Cost-table numbers (`data/curated/costs.json`) | S10b | Source URLs and figures confirmed by the user; no invented numbers |
| Committing `articulation.db` (est. tens of MB) and `corpus.db` | S9c, S11 | Confirm artifact size is acceptable before the commit |
| Commits | every split | Each split ends in exactly one commit per its kickoff prompt |

Everything else in these docs (edits, deletions listed in doc 01, offline builds from fixtures, tests) is pre-approved by the user's 2026-07-31 instructions.

## Standing decision points for the user (not for executors)

1. Whether to delete the dormant `contracts/corpus_document.py` stack once increment 7 confirms the reduced-scope retrieval never uses it.
2. Whether `scripts/spike_fetch.py` (the retired spike tool) should be deleted or kept as a historical record.

Resolved: the `beautifulsoup4` removal (approved and executed 2026-08-01, after S9a).
