# Increment 7: Fuzzy Course Matcher

Goal: the deterministic per-institution FTS5/BM25 index over `cc_courses` in `corpus.db`, plus the fixed-threshold resolver that classifies every lookup as `exact`, `fuzzy_match`, or `unresolved`.
Binding mechanism references: TR 1.4 (match-expression compilation, `-bm25` ordering, tie-breaks, FTS5 fail-fast) with the "Starmap deltas (RAG)" reduced even further by the pivot, and the vocabulary-gate axiom in `CLAUDE.md`.
No LLM, no network, no embeddings (axioms); SQLite is never faked in tests.

## Reduced scope, locked

The pivot reduces TR section 1 to the FTS5/BM25 kernel only: NO document registry, NO snapshots, NO chunking, NO normalization pipeline, NO eval harness with floors.
Rationale, recorded: the corpus rows are `cc_courses` projections regenerated deterministically from `articulation.db` on every build, so the append-only registry and snapshot pinning protect nothing here; the retrieval behavior is pinned by fixture-driven tests instead of a labeled eval.
`contracts/corpus_document.py` is NOT used by this increment (overview doc, "Out of scope"); after this increment lands, remind the user of standing decision point 1 (its deletion).

What survives from TR 1.4 verbatim: the match-expression quoting rule (bag-of-words, `\w+` tokens, each double-quoted, joined with `" OR "`; operators become literals; no tokens compiles to the empty string and returns an honest empty result), `-bm25(...) AS score` with `ORDER BY score DESC` and a deterministic tie-break, ranks assigned 1..n, and the FTS5 construction-time probe that raises rather than degrades.

## `retrieval/` modules

### `retrieval/errors.py`

- `RetrievalError(StarmapError)` base.
- `Fts5UnavailableError(RetrievalError)`: raised at index construction by an in-memory `CREATE VIRTUAL TABLE ... USING fts5` probe; `reason_code = RetrievalCode.FTS5_UNAVAILABLE`; NEVER caught to degrade (TR 1.6 policy).
- `InstitutionNotIndexedError(RetrievalError)`: search against an institution with no built index; `reason_code = RetrievalCode.INSTITUTION_NOT_INDEXED`; carries the institution id.

### `retrieval/index.py`

`CourseIndex(db: SqliteDatabase)`; FTS5 probe in the constructor; `ensure_schema(component="corpus", version=1, statements=...)`:

```sql
CREATE TABLE IF NOT EXISTS cc_course_rows (
    institution_id INTEGER NOT NULL, course_code TEXT NOT NULL, prefix TEXT NOT NULL,
    number TEXT NOT NULL, title TEXT NOT NULL, units_min REAL NOT NULL, units_max REAL NOT NULL,
    PRIMARY KEY (institution_id, course_code));
CREATE TABLE IF NOT EXISTS index_builds (
    institution_id INTEGER PRIMARY KEY, course_count INTEGER NOT NULL);
```

Plus, per institution at build time: `CREATE VIRTUAL TABLE IF NOT EXISTS cc_courses_fts_<id> USING fts5(code, title)`.
Why one FTS table PER INSTITUTION (the TR 1.4 per-snapshot argument, transplanted): BM25 term statistics are corpus-wide, so a shared table would let one college's catalog shift another's scores; with per-institution tables a result is a pure function of (query, institution).
Table-name safety: `<id>` is interpolated only after validating the institution id is a positive `int` (`isinstance(x, int) and x > 0`); anything else raises `ValueError` (the integer check is what makes the f-string-into-SQL safe, mirroring TR 1.4's regex rule).

`build(institution_id, courses: Sequence[CcCourse]) -> int`, idempotent: inside one transaction, an existing `index_builds` row returns the stored count unchanged (rows regenerate only through a fresh db build); otherwise insert `cc_course_rows` in sorted `course_code` order, insert each into the FTS table with `rowid` = the just-inserted `cc_course_rows` rowid (the join key everywhere), and record the build row.
Two-column weighting: none (equal weights); locked as the default until real transcript data argues otherwise.

`search(institution_id, query: str, k: int = 5) -> list[SearchHit]` with `SearchHit` frozen `(course_code, title, units_min, units_max, score, rank)`:

- Compile the query per the TR 1.4 bag-of-words rule; empty compilation returns `[]`.
- `SELECT ..., -bm25(cc_courses_fts_<id>) AS score FROM cc_courses_fts_<id> f JOIN cc_course_rows c ON c.rowid = f.rowid WHERE c.institution_id = ? AND cc_courses_fts_<id> MATCH ? ORDER BY score DESC, c.course_code ASC LIMIT ?`.
- Ranks 1..n by enumeration; unbuilt institution raises `InstitutionNotIndexedError`.

### `retrieval/resolve.py`

The fixed-threshold resolver; its result vocabulary is exactly the transcript-gate vocabulary (`exact` / `fuzzy_match` / `unresolved`) so the Week 2 validator consumes it without translation.

```python
FUZZY_ACCEPT_RATIO = 0.6   # locked; changing it is a spec change, not a tuning knob
FUZZY_CANDIDATES_K = 5     # locked
```

`Resolution` frozen: `status: Literal["exact", "fuzzy_match", "unresolved"]`, `course_code: str | None`, `title: str | None`, `units_min: float | None`, `units_max: float | None`, `ratio: float | None` (None for exact and unresolved-with-no-candidates).

`resolve_course(index, institution_id, *, code: str | None, title: str | None) -> Resolution`, locked algorithm:

1. At least one of `code`/`title` must be a non-empty string; else return `unresolved` (total function, no raise).
2. Exact gate: if `code` normalizes under `normalize_course_code` AND the normalized code exists in `cc_course_rows` for the institution, return `exact` with that row; a code that fails normalization falls through (tolerant input, strict store).
3. Fuzzy gate: query text = the space-join of whichever of `code`, `title` are present; take `search(institution_id, query_text, k=FUZZY_CANDIDATES_K)`; for each hit compute `ratio = difflib.SequenceMatcher(None, casefold_key(query_text), casefold_key(f"{hit.course_code} {hit.title}")).ratio()` (with `casefold_key` from `contracts/dedup.py`, so joins agree everywhere); pick the best by `(ratio desc, score desc, course_code asc)`.
4. Best ratio `>= FUZZY_ACCEPT_RATIO` -> `fuzzy_match` with the hit and its ratio; below, or no hits -> `unresolved` (with the best ratio when one exists).

`difflib.SequenceMatcher` is stdlib, pure, and deterministic; no new dependency (overview doc).

## Build stage: `corpus.db`

Extend `backend/scripts/build_articulation.py` with `--stage corpus` (running last under `--stage all`): read every institution's `cc_courses` from `articulation.db` through the doc 02 read surface, build the per-institution indexes in sorted institution-id order into `data/corpus.db`, `VACUUM`, done.
`--check` extends to `corpus.db` with the same canonical-dump comparison; `common/dbdump.py` already excludes FTS shadow-table rows while keeping the declared virtual-table DDL, so no dump changes are needed.
`corpus.db` is a committed read-only artifact; the local `make build-check` gate covers both dbs (overview doc, "Committed-artifact identity").

The vocabulary gate, restated as the wiring rule for Week 2 (locked now so the API increment cannot re-derive): `cc_course_rows` in `corpus.db` IS the projection served by `GET /api/cc/{id}/courses` autocomplete AND consumed by the transcript resolver; one table, two consumers, never a second extraction from `articulation.db` at request time.

## Tests

`backend/tests/retrieval/`, all against real temp SQLite files (never faked):

- Probe: constructing against a SQLite build without FTS5 raises `Fts5UnavailableError` (skip-marked if the CI SQLite always has FTS5; the probe logic is still unit-tested by monkeypatching the probe statement to a bad one).
- Build idempotency: second `build` returns the stored count and changes nothing (`canonical_dump` equal before and after).
- Determinism: same query twice, byte-equal serialized results; reversing the insert order of the input courses changes nothing (sorted-insert rule).
- Per-institution isolation: the same query against two institutions with overlapping titles scores independently; building a second institution leaves the first institution's serialized results byte-identical (the TR 1.4 two-snapshots pin, transplanted).
- Tie-break: two courses with identical BM25 scores order by `course_code` ascending.
- Compilation: punctuation-only query returns an honest empty result; FTS operators (`NEAR`, `*`, quotes) in user text are treated as literals.
- Resolver, fixture-driven (`backend/tests/fixtures/retrieval/resolve_cases.json`, one entry per case: inputs, expected status, expected code): exact code hit; exact wins even when fuzzy would match something else; misspelled title resolves (`"diferential equasions"` -> the differential equations row); code-only fuzzy (`"MATH 2AH"` typo `"MATH 2 AH"` normalizes exact, `"MTH 2A"` goes fuzzy); threshold boundary pinned with a constructed pair just above and just below `0.6`; garbage input -> `unresolved`; empty inputs -> `unresolved`.
- Resolver determinism: identical calls return equal `Resolution` objects; tie between candidates resolves by the locked key.
- Corpus stage: build from a temp `articulation.db` seeded with the captured-fixture normalization output; `--check` passes on itself and fails after a row mutation; `cc_course_rows` contents equal the `cc_courses` projection exactly (the gate test: one projection, no re-derivation).

## Exit criteria

- `make check` green; the resolver case file proves the threshold semantics (exact, else fuzzy above 0.6, else unresolved).
- `data/corpus.db` built by `--stage corpus` and committed (size confirmed with the user); `make build-check` covers both artifacts.
- Known misspellings and title-only entries resolve correctly in the fixture cases; per-institution isolation pinned.
