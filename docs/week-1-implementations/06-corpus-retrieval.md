# Increment 6: Corpus and Retrieval

Goal: the deterministic retrieval stack (registry, snapshots, chunking, FTS5/BM25) over a corpus built from the catalog, with a hand-labeled eval and measured floors.
Binding mechanism reference: TR section 1 with the "Starmap deltas (RAG)" applied; deltas restated below are decisions, not suggestions.
No network, no LLM anywhere in this increment (axiom).

## Applied deltas (locked)

- Drop: embeddings, vectors, fusion, source_claims, track tags (no `track_tags` column, no filters), the web-manifest ingest tool (TR 1.7 does not apply; the catalog build IS the ingest).
- Keep intact: single hash definition, derived ids, append-only registry with typed conflict, hash-check on register AND read, snapshot pinning with chunking params in the identity, `structure_v1` chunking, per-snapshot FTS tables, match-expression quoting, `-bm25` ordering with chunk-id tie-break, FTS5 fail-fast at construction, eval harness with measured floors.
- Normalization: implement `normalize_text` only (TR 1.5); skip `html_to_text` and the sniffing router, because corpus text is composed from already-parsed catalog fields.
  Record this in the module docstring.
- Chunking params locked: `algorithm="structure_v1"`, `target_chars=1600`, `overlap_chars=200`; most course docs will be single-chunk, and that is fine.

## `retrieval/` modules

- `retrieval/ids.py`: `content_hash_for`, `derive_doc_id`, `derive_snapshot_id`, `derive_chunk_id`, `chunking_fingerprint`, formulas verbatim from TR 1.1-1.3.
- `retrieval/registry.py`: the Protocol from TR 1.1 minus the `track` parameter, `InMemoryRegistry`, `SqliteRegistry` (tables per TR 1.1 sketch), one parametrized test suite over both.
  Registry storage component: `ensure_schema(component="corpus", version=1, ...)` inside `corpus.db`.
- `retrieval/normalize.py`: `normalize_text` per TR 1.5, idempotency asserted by test.
- `retrieval/chunking.py`: `ChunkingParams` contract, `Chunk` frozen type, `chunk_text`, `chunk_snapshot` per TR 1.3; the full TR test list is the required test list.
- `retrieval/index.py`: per TR 1.4 minus track filtering; snapshot-id regex validated before table-name interpolation; `Fts5UnavailableError` probe at construction; search returns `(chunk_id, doc_id, score, rank)` rows ordered `score DESC, chunk_id ASC`; ranks 1..n; unbuilt snapshot raises typed.
- `retrieval/errors.py`: the TR 1.6 error table, subclassing `StarmapError`, reason codes from `CorpusCode`.
- `retrieval/eval.py` + `backend/scripts/run_retrieval_eval.py`: per TR 1.8 with the label delta below.

## Corpus document composition (build stage 5)

`catalog/build_corpus.py`, invoked by `build_catalog.py --stage corpus`, writing `data/corpus.db`.

Per course (sorted by course code), one document:

- `title` = `"<code> <title>"`.
- Text blocks joined by blank lines: title line; description; `Prerequisites: <prereq_prose>` when present; `Fulfills: <group names>` computed from requirement-group membership (groups listing the course, names sorted).
- Text is passed through `normalize_text` before hashing and registration.
- `source_url` = `<bulletin_url>#<course_code with space replaced by "-">` (locked: gives every course doc a unique URL so URL-keyed eval labels work; TR 1.8 keys labels by source URL).
- `source_type="bulletin_course"`; `license_note="Columbia College Bulletin, public web page; contest demo use"`; `source_published_date=None`.
- `date_collected` = the `date_fetched` recorded in `data/raw/manifest.jsonl` for the course's department page (NOT the build date; locked so rebuilds from the same cache derive identical doc ids and the artifact stays byte-stable).

Per requirement group (sorted by id), one document: title = `"<major name>: <group name>"`, text = group name + member codes with titles + note text; `source_type="bulletin_requirement"`; same URL-fragment scheme on the dept page (`#rg-<requirement_group_id>`).

Stage steps: register all docs (idempotent re-register is a no-op); create ONE snapshot over all registered docs with the locked params (idempotent create returns the stored one); build the FTS index; write `live_snapshot_id` into a `corpus_meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)` table; `VACUUM`.
`--check` covers `corpus.db` via `canonical_dump` like `catalog.db`.

## Eval

`backend/evalsets/retrieval_queries_v1.json`, shape per TR 1.8 minus the `track` field; `query_id` pattern `^rq_[a-z0-9_]+$`.
Author ~10 interest-style queries against real catalog content after stage 5 runs, covering the demo majors and breadth, e.g. machine learning, systems programming, econometrics, creative writing, music theory, cognitive science; label 2-5 relevant course-doc source URLs each, with dated judgment notes.
Metrics per TR 1.8: doc-level collapse, `recall@k`, `reciprocal_rank`, binary-gain `nDCG@k`, 4-place rounding; label URL absent from snapshot is a typed error.
Runner flags per TR 1.8: `--queries --db --snapshot --k --strict` plus the three floor flags given together; floors are MEASURED on the first pinned run, recorded in the evalset comment with provenance, then wired into `make check` as `make retrieval-eval` invoked with `--strict` (add the target and include it in `check` once floors exist).

## Tests

- Registry parametrized suite: TR 1.1 list (round trip, no-op re-register, typed conflict leaving store unchanged, hash-mismatch stores nothing, insertion order, reopen persistence, corrupted-text read raises).
- Chunking: TR 1.3 list verbatim (byte-identical re-chunk, exact-slice coverage, breadcrumbs, 250/80 hard split, overlap bounds, zero-overlap disjointness, params change all ids, empty text).
- Index: TR 1.4 list (determinism, two-snapshots-independent byte-pin, tie-break, k bounds, punctuation-only empty result, operator injection as literals, provenance round trip, unbuilt snapshot typed error, FTS5 probe).
- Eval: hand-computed metric values; unknown label raises; harness-can-fail (deliberately broken floor fails strict run).
- Corpus build: fixture mini-catalog to corpus round trip; doc-id stability across two builds from the same cache manifest; `Fulfills` block content; snapshot idempotency; `live_snapshot_id` written.

## Exit criteria

- `make build-data` through stage 5 green offline; `corpus.db` committed with one snapshot.
- BM25 spot queries return sane results for 3 recorded interest queries (log them in `docs/notes/retrieval_spotchecks.md`).
- Eval floors measured, recorded, and enforced via `--strict` in `make check`.
- `--check` proves `corpus.db` canonical-dump identity on regeneration.
