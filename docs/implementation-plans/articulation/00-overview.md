# Articulation Increments: Overview

This folder turns increments 4-7 of `docs/IMPLEMENTATION_ROADMAP.md` (the pivoted Foothold roadmap) into executable implementation plans.
One doc per increment, written for a less-capable executor model per `AGENTS.md` "Implementation Plan Conventions": every design decision is locked here; the executor implements and does not design.
Authored 2026-07-31; all cited symbols, file paths, and fixture facts verified against `main` at commit `4762feb` on that date.

Authority order for an executing session: user chat instructions, `CLAUDE.md`, `AGENTS.md`, `docs/FOOTHOLD_PATHFINDERS_PLAN.md` + `docs/FOOTHOLD_TECH_REFERENCE.md`, these docs, `docs/specs/`, code.
Citations like "TR 4.5" mean `docs/FOOTHOLD_TECH_REFERENCE.md` section 4.5 and are binding pointers, not optional background.
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

An eighth fixture was captured later, in split S9c, from the live corridor rather than the spike:

| File | What it pins |
|---|---|
| `agreement_with_advisements_4_to_39_y76.json` | College of Marin -> San Jose State, Computer Science B.S. The POPULATED advisement shape `{"content": str, "position": int}`, which no spike capture could show because all seven are empty at every attribute level. Four sending-course advisements on two articulations. Of its five requirement groups, the two `Following` ones (positions 3 and 7) store as complete-all from S9d onward and the three `NFromArea` ones (1, 5, 9) remain excluded; the single group-level advisement rides on position 5, an excluded group, so it still reaches no one as a satisfied requirement. |

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
    r"^[A-Z][A-Z0-9&/.\-]{0,9}(?: [A-Z&][A-Z0-9&/.\-]{0,9}){0,2}"
    r" -?[A-Z]{0,2}[0-9]{1,4}(?:\.[0-9]{1,2})?(?:[A-Z+\-][A-Z0-9+\-]{0,3})?"
    r"(?: [A-Z]{1,2})?$"
)
```

This block is the SHIPPED pattern as of S9d, re-synchronised against `contracts/codes.py`.
It had drifted: the version recorded here through S9c wrote the number's trailing group as `[A-Z0-9+\-]{0,3}`, while the code shipped `(?:[A-Z+\-][A-Z0-9+\-]{0,2})?`, which is stricter because it forbids a trailing group that opens with a digit and so keeps `MATH 12345` invalid.
The code was right and the doc was stale; do not "restore" the looser form.

- Shape: one to three prefix tokens (letters, then letters/digits plus `&/.-`), one number token (optional leading `-`, up to 2 leading letters, 1-4 digits, an optional decimal part, up to 3 trailing letters/digits/`+`/`-`), and an optional trailing campus-suffix token of 1-2 letters.
- Covers every code in the captures: `MATH 1A`, `MATH 2AH`, `STAT C1000H`, `CIS 22C`, `CIS 22CH`, `CSE 15L`, `MATH 20E`, `CSE 11`.

The first three clauses of that pattern were WIDENED in S9c, after the full corridor build excluded 1,624 articulations (about 6%) as `course_code_unparseable` across 150 distinct codes.
The original regex was designed from the De Anza-to-UCSD captures alone, and California course codes are more varied than that one pair shows:

| Shape | Corridor count | Examples |
|---|---|---|
| Digit inside a prefix token | 1,006 | `BUS1 20`, `BUS2 90` (San Jose State business departments), `IN4MATX 43` (UCI) |
| Trailing campus-suffix token | 338 | `MATH 151 F` (Fullerton), `CSCI 133 C` (Cypress), `CHEM 211 AC` |
| Leading hyphen on the number | 190 | `MATH -04A`, `MATH -08` |
| Decimal number | 26 | `BIO 2.1`, `CS 17.11` |
| `+` or embedded `-` suffix | 19 | `MATH 103E+`, `CIST 004B1`, `MATH 120-S` |

A separate 42 were a bug on OUR side rather than a regex gap: ASSIST publishes padded values like `courseNumber: "C1000 "`, and the normalizer passed the raw strings to the contract while deriving the code from the collapsed ones.
`normalize._course_row` now strips and collapses both parts before validation, which is why `COURSE_NUMBER_PATTERN` admits an internal space (`C1000 H`) but never a leading or trailing one.

The regex is deliberately looser than it was, and that is a real cost: a genuinely malformed code is now likelier to pass than to be excluded.
The compensating check is that a code still has to round-trip `course_code == course_code_from_parts(prefix, number)` on every one of the three models that store the split pair.
- `normalize_course_code(raw)` keeps its current contract: uppercase, collapse internal whitespace runs to one space, strip, then fullmatch; `ValueError` naming the input on failure.
- New helper in the same module: `course_code_from_parts(prefix: str, number: str) -> str` returning `normalize_course_code(f"{prefix} {number}")`; this is the single derivation every contract and normalizer uses.
- A code that fails normalization at build time is a per-articulation typed exclusion (`course_code_unparseable`), counted in the build report, never fatal (fault-isolation axiom).

### Reason-code families (one-time pivot exception to append-only)

The append-only-forever rule in `docs/specs/reason_codes.schema.md` exists so persisted or logged codes never dangle.
`PrereqExtractionCode`, `BuildCode`, and `CorpusCode` never shipped a producer and no artifact or log row carries their values; their consumers are retired by the pivot before ever existing.
Locked: increment 4 DELETES those three families under the same 2026-07-31 pivot approval that retires the Columbia-shaped contracts, and records this paragraph's rationale in the spec as a one-time exception.
`LlmReasonCode` is unchanged (its consumer, the Week 2 LLM backbone, is alive).
Increment 4 ADDS three families (exact members locked in doc 01): `EvaluationFindingCode`, `AssistBuildCode`, `RetrievalCode`, plus the `TriageBucket` enum and the `BUCKET_FOR_CODE` mapping.

### Advisements: RESOLVED in S9c (was fixture-pending)

Per the spike doc, `attributes` lists exist at four levels (articulation, sending-articulation, group, course) and are the advisement carrier, but every SPIKE captured list is EMPTY, so the mapping was deferred rather than guessed.
The first live corridor fetch settled it. What S9c measured, and what now binds:

- A text advisement is exactly `{"content": str, "position": int}`; the corridor publishes 11 distinct strings of it ("Minimum grade required: C or better", "Complete entire sequence at same institution prior to transfer", ...). `advisement_texts` maps that shape, sorted by `position`, verbatim apart from an outer strip.
- SEVEN levels feed it, not four. A corridor-wide sweep found real prose at three levels nothing was reading: `courseAttributes` (9 instances), template group `attributes` (46), and template cell `attributes` (2). Those were silent drops, which the axiom forbids, and they are now mapped. `receivingAttributes` was empty in all 364 payloads swept and remains unmapped, named here so it reads as examined rather than missed.
- AMENDED in S9e: the S9c sweep was a 364-payload sample, and a full-corridor sweep (31,272 payloads) found five more populated levels it missed - `seriesAttributes` on articulations, `attributes` on template sections and rows, and `courseAttributes`/`seriesAttributes` on template cells (41,246 entries at the last alone, "Minimum grade required: B or better"). All five are mapped as of S9e, so TWELVE levels feed the gate. `receivingAttributes` turned out to be populated too but is a verbatim mirror of the articulation-level lists (sampled: 65 of 65 identical), so it stays unread along with `requirementAttributes`, which sits only on `Requirement` cells that already exclude their group. See `docs/notes/articulation_spotchecks.md` section 11.
- The gate NARROWED, it did not disappear. Anything that is not the pinned shape still raises `advisement_shape_unknown`, and that is load-bearing: template sections carry a structurally different `{"type": "NFollowing", "amount": 2.0, "selectionType": "Select"}` under the same field name, meaning "select 2 of the following". Flattening it to prose would invent an advisement; skipping it would let a group that means "select 2 of" read as "complete all of". So the group is excluded and reported. Modelling N-from semantics is deferred to a later increment.
- The note-leaf MECHANISM (contract shape, evaluator semantics) is unchanged; group and course texts still become `NoteLeaf`s INSIDE the group node.
- Nothing anywhere silently satisfies, drops, or paraphrases an advisement (axiom).

### Committed-artifact identity at ASSIST scale

`articulation.db` and `corpus.db` follow the canonical-logical-dump identity from `docs/week-1-implementations/README.md` ("Committed-artifact identity") via `common/dbdump.canonical_dump`.

Packaging deviation, locked in S9d: the COMMITTED form of the articulation artifact is `data/articulation.db.gz`, and `data/articulation.db` itself is gitignored.
GitHub hard-rejects any file over 100 MB on push, and the fifteen-campus corridor builds to ~319 MB, so committing the database directly is not merely expensive, it is impossible on this remote.
Gzip takes it to ~35 MB, which keeps the artifact inside a plain `git clone` and avoids Git LFS, whose absence on a judge's machine would turn the checkout into a pointer file and a broken build.
`make build-data` writes both files; `make unpack-data` restores the database from the gzip and is the first command to run on a fresh clone.
Artifact identity is unchanged and still defined over the canonical logical dump, never over the compressed bytes: `--check` decompresses nothing and compares dumps of rebuilt databases, exactly as it did before, because gzip output may legitimately differ across zlib builds for the same reason SQLite bytes differ across library versions.
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
