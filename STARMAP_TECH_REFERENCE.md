# Starmap Technical Reference (from Agentic-Calendar)

This document is the written design record the Starmap build agent works from.
It captures, in prose and sketches, everything needed to re-implement three subsystems of Agentic-Calendar ("Loop") as smaller, purpose-built modules: the RAG pipeline, the pathway/knowledge-map feature, and the onboarding flow, plus the cross-cutting kernels they share.
Read it together with `STARMAP_PATHFINDERS_PLAN.md` (the product/architecture plan); this file is the mechanism-level companion.

Rules of engagement:

- Contest terms forbid copying code from Agentic-Calendar; every line in the Starmap repo must be newly written.
- Therefore this document contains no verbatim source, only data shapes, invariants, algorithm steps, edge-case policies, test strategies, and pseudocode.
- "Ref:" pointers name Agentic-Calendar files for optional deeper study only; the intent is that you never need to open them.
- Every section ends with a "Starmap deltas" note saying what to drop, shrink, or change for Starmap.

Path corrections vs older notes: the corpus manifest lives at `backend/corpus/manifest_v1.json` and the eval query sets at `backend/evalsets/` (both under `backend/`, not the repo root).

---

## 1. RAG pipeline

Ref: `backend/src/agentic_calendar/retrieval/` (`registry.py`, `sqlite_registry.py`, `chunking.py`, `index.py`, `normalize.py`, `errors.py`, `eval.py`), `tools/ingest_corpus.py`, `tools/run_retrieval_eval.py`.

The pipeline is four layers, each a pure function of the layer below:

1. An append-only, content-hash-verified document registry (text + metadata).
2. Immutable snapshots that pin a document set plus a chunking configuration.
3. Deterministic chunking of a snapshot's members.
4. A per-snapshot FTS5/BM25 index, plus a labeled eval harness over pinned snapshots.

The governing invariant: no LLM anywhere in the retrieval path.
Because every stage is deterministic over checked-in data, the retrieval eval is a pure function and can gate merges directly.

### 1.1 Document registry

One hash definition for the whole system:

```
content_hash_for(text) = sha256(text.encode("utf-8")).hexdigest()
```

Callers always hash the NORMALIZED text (section 1.5); normalization is the ingest tool's job, not the hash function's.

Document identity is derived from provenance:

```
derive_doc_id(source_url, date_collected) =
    "doc_" + sha256(f"{source_url}\n{date_collected.isoformat()}")[:16 hex chars]
```

Consequence: the same URL fetched on a new day is a NEW document (pages change); the same URL on the same day is the SAME document, which makes re-ingest hash-idempotent.

`CorpusDocument` contract (frozen, extra=forbid): `doc_id` (pattern `^doc_[0-9a-f]{16}$`), `source_url` (non-empty), `source_type` (closed enum, computed by a deterministic URL classifier, never by the LLM and never trusted from the manifest), `license_note` (non-empty; no license basis means no registration), `date_collected` (date), `source_published_date` (date or null), `track_tags` (non-empty unique list), `content_hash` (`^[0-9a-f]{64}$`), `title` (non-empty).
Model validators: `doc_id` must equal its derivation; `track_tags` unique; `source_published_date` must not be after `date_collected`.
The document TEXT is deliberately not a contract field, so the metadata schema stays small and exportable; text lives in the registry beside the record.

Contract-vs-registry responsibility split (a pattern used everywhere):

- The contract owns shape and internal self-consistency (patterns, derivation checks, uniqueness).
- The registry owns what the contract cannot see: the stored text really hashes to `content_hash` (checked on register AND on read), registered documents are immutable, and re-registering an identical document is a no-op.

Registry protocol (a Protocol with an in-memory twin and a SQLite twin, tested by one parametrized suite):

```
register(document, *, text) -> bool          # True = newly stored, False = identical no-op
get_document(doc_id) -> CorpusDocument | None
get_text(doc_id) -> str | None
list_documents(*, track=None) -> list[CorpusDocument]     # insertion order
create_snapshot(doc_ids, *, created_at, chunking_params) -> CorpusSnapshot
get_snapshot(snapshot_id) -> CorpusSnapshot | None
list_snapshots() -> list[CorpusSnapshot]
```

There is deliberately NO delete or update surface.
A corpus change is a new fetch (new `doc_id`) and a new snapshot; this mirrors plan-version discipline elsewhere in the system.

SQLite storage sketch (payload = the canonical Pydantic JSON dump; reads rebuild through `model_validate_json` so a round trip is contract-validated, never trusted):

```sql
CREATE TABLE IF NOT EXISTS corpus_documents (
    doc_id TEXT PRIMARY KEY, payload TEXT NOT NULL, text TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS corpus_snapshots (
    snapshot_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
```

Register algorithm: hash-check the text against the record BEFORE the transaction; inside one write transaction, explicit `SELECT` for the existing row; present and equal model means return False; present and different means raise a typed `CorpusDocumentConflictError`; absent means insert.
The existence check is an explicit SELECT inside the insert transaction (not a PK-violation catch) so a concurrent register cannot slip past and the error stays typed, never a leaked `sqlite3.IntegrityError`.
`get_text` re-validates the record and re-checks the hash of stored text, so on-disk corruption raises instead of serving wrong evidence.

Tests that pin it: one suite parametrized over both registry implementations asserts round trips, no-op re-register, typed conflict that leaves the store unchanged, hash-mismatch register that stores nothing, insertion-order listing, and SQLite state surviving a reopen.

### 1.2 Snapshot model

A snapshot is the pinning unit for eval reproducibility: evals run against a `snapshot_id`, never "whatever the corpus is right now".

`ChunkingParams` (frozen): `algorithm` (a closed literal, e.g. `"structure_v1"`), `target_chars` (> 0), `overlap_chars` (>= 0), with a validator requiring `overlap_chars < target_chars` (equal overlap would make chunking non-progressing).
`target_chars` is a soft maximum (a chunk closes before the unit that would overshoot; only a single oversized unit is hard-split); `overlap_chars` is an upper bound (overlap snaps to unit boundaries).
A change to chunking BEHAVIOR is a new `algorithm` value, not a silent edit.

```
chunking_fingerprint(params) = f"{algorithm}:{target_chars}:{overlap_chars}"
derive_snapshot_id(content_hashes, params) =
    "snap_" + sha256("\n".join([fingerprint, *sorted(set(content_hashes))]))[:16 hex chars]
```

The derivation is member-order-independent and de-duplicating by construction.
`chunking_params` is part of the identity because chunks, indexes, labels, and metrics are only valid for one exact chunking configuration; re-chunking is a new snapshot, so an eval can never silently run against re-chunked data.

`CorpusSnapshot` contract: `snapshot_id` (`^snap_[0-9a-f]{16}$`), `created_at`, `doc_ids` (non-empty, sorted, unique), `content_hashes` (parallel to `doc_ids`, each a well-formed sha256), `chunking_params`.
Validators re-derive and check the id, so the pin is self-contained: the contract verifies identity without the registry.
Creating a snapshot whose derived id already exists returns the STORED snapshot with its original `created_at` (idempotent create); empty membership is a typed error; unresolvable members are a typed error listing the missing ids.

### 1.3 Deterministic chunking (`structure_v1`)

Defaults: `target_chars=1600`, `overlap_chars=200`, explicitly labeled heuristic priors (about 400 English tokens), meant to be an eval ablation, not a tuned constant.

Chunk identity:

```
derive_chunk_id(doc_id, ordinal, params) =
    "chunk_" + sha256(f"{doc_id}\n{ordinal}\n{chunking_fingerprint(params)}")[:16 hex chars]
```

Re-chunking the same text under the same params reproduces the same ids; changing params changes EVERY id, so results from different chunkings can never be silently mixed.

Output type: a frozen `Chunk(chunk_id, doc_id, ordinal, text, start_char, end_char, breadcrumb)`.

Algorithm, operating on already-normalized text:

1. Compute character spans for every newline-split line (offsets, never substrings).
2. Walk lines building SECTIONS: a blank line closes the current paragraph; a line matching the markdown ATX heading pattern `^(#{1,6})\s+(.*\S)` closes the current section, pops the heading stack down to its level, pushes `(level, title)`, and emits the heading line itself as an atom of the new section.
   A section's breadcrumb is the heading-stack titles joined with `" > "`, or null when no heading is open.
3. Within a section, fold each paragraph (run of non-blank lines) into ATOMS: the whole run is one atom if its span fits `target_chars`; otherwise fall back to its individual lines; a single line longer than `target_chars` is hard-split every `target_chars` characters.
   HTML-derived text arrives as one line per source block element (see 1.5), so the per-line path is the common path for web pages.
4. Greedy-pack each section's atoms into groups: start a new group when adding the atom would make `atom.end - group_start > target_chars`.
5. Overlap: for every group after a section's first, extend its start backward over the previous group's trailing atoms while `previous_group_end - atom.start <= overlap_chars`.
   Overlap snaps to atom boundaries and never crosses a section boundary.
6. Assign contiguous ordinals from 0 in document order; each chunk's text is exactly `text[start:end]`.

Invariants: every chunk is an exact contiguous slice of the stored normalized text (auditability: an excerpt can always point back into the exact document region); chunks never span a section boundary; each carries its breadcrumb.

`chunk_snapshot(registry, snapshot)` processes members in the snapshot's canonical sorted order under the PINNED params; a member the registry cannot resolve raises the typed unknown-document error, because a snapshot must never silently chunk to fewer documents than it pins.

Tests that pin it: byte-identical re-chunk; exact-slice and full-coverage assertions (every non-newline character covered, in strictly advancing order); breadcrumbs and the no-cross-section rule; the hard-split case (a 250-char line at target 80 splits 80/80/80/10); overlap bounded with strictly advancing chunk ends; zero overlap means disjoint chunks; different params give a zero chunk-id intersection; empty text gives no chunks.

### 1.4 FTS5/BM25 index

Storage sketch (schema component versioned via `ensure_schema`, see 4.3):

```sql
CREATE TABLE IF NOT EXISTS retrieval_chunks (
    snapshot_id TEXT NOT NULL, chunk_id TEXT NOT NULL, doc_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL, start_char INTEGER NOT NULL, end_char INTEGER NOT NULL,
    breadcrumb TEXT, track_tags TEXT NOT NULL, text TEXT NOT NULL,
    PRIMARY KEY (snapshot_id, chunk_id));
CREATE TABLE IF NOT EXISTS retrieval_index_builds (
    snapshot_id TEXT PRIMARY KEY, chunk_count INTEGER NOT NULL);
-- plus, per snapshot, created at build time:
CREATE VIRTUAL TABLE IF NOT EXISTS retrieval_fts_<hex16> USING fts5(text);
```

Why one FTS table PER SNAPSHOT: BM25 ranking depends on corpus-wide term statistics, so a shared table would let an unrelated ingestion silently shift another snapshot's scores.
With a dedicated table, results are a pure function of (query, snapshot); the pinning test indexes a second snapshot and asserts the first snapshot's serialized results stay byte-identical.

Table-name safety: the snapshot id is validated against `^snap_([0-9a-f]{16})$` before the hex is interpolated into the table name; a malformed id raises.
The regex validation is what makes the f-string-into-SQL safe (the id is never user text).

Build (idempotent): all registry reads happen BEFORE the write transaction opens (the shared-database rule: transactions never nest).
Inside one transaction: if a build row already exists for the snapshot, return the stored count (the snapshot is immutable, so the derivation cannot have changed); otherwise create the virtual table, insert each chunk row, and insert into the FTS table with `rowid = ` the just-inserted `retrieval_chunks` rowid.
That rowid aliasing is the join key everywhere (`JOIN retrieval_chunks c ON c.rowid = f.rowid`).

Match-expression compilation (deterministic, the whole "query understanding" layer):

- Bag-of-words: find all `\w+` tokens (Unicode) in the lowercased query, wrap each in double quotes, join with `" OR "`.
  Quoting makes FTS5 operators (`NEAR`, `AND`, `OR`, `*`, parentheses) literals, never syntax; `System-design, C++!` compiles to `"system" OR "design" OR "c"`.
  No word tokens compiles to the empty string and the caller returns an honest empty result rather than raising.
- Phrase form: one double-quoted phrase of space-joined tokens (`"power bi"`), used where adjacency semantics matter (alias matching).
  `c++` degrades to `"c"`; that noise is a documented property of the alias, not the compiler.

Search: SQL selects `-bm25(<fts_table>) AS score` (FTS5 returns more-negative-is-better, so the negation makes higher-is-better), then `ORDER BY score DESC, chunk_id ASC LIMIT k`.
No column weights (single indexed column).
Ranks are assigned 1..n by enumeration, and the result envelope contract re-validates the ordering rule on the way out, so a producing index physically cannot emit an out-of-order result.
Searching an unbuilt snapshot is a typed `SnapshotNotIndexedError`.

Track filtering (Loop-specific): tags stored as a delimiter-wrapped marker string `",tag1,tag2,"` and filtered with `instr(track_tags, ',<tag>,') > 0` (delimiters avoid prefix collisions).

Tests that pin it: determinism and snapshot stamping; contiguous ranks and ordered scores; exact ties break by `chunk_id` ascending; `k` bounds; punctuation-only query gives an honest empty result; FTS operators in user text are treated as literals; `get_chunk` round-trips provenance and its text equals the registry slice; two-snapshots-score-independently.

### 1.5 Normalization

Four functions, stdlib-only, all pure:

- `normalize_text(text)`: Unicode NFC; per-line collapse of inline whitespace runs to a single space; strip each line; collapse runs of blank lines to exactly one (paragraph break); drop trailing blank lines; join with `\n`.
  Idempotent (asserted by test).
- `html_to_text(html)`: a stdlib `HTMLParser` subclass with entity conversion on; drops the entire content of `script`/`style`/`noscript`/`template` via a depth counter; emits a newline on the start AND end of every block-level tag (a list of about 30: paragraphs, headings, list items, table cells, `br`, `hr`, `pre`, etc.); then runs `normalize_text`; then drops ALL blank lines, because in HTML whitespace is not semantic (structure lives in tags) and adjacent block boundaries must not fabricate paragraph breaks.
  Consequence: HTML-derived documents are one line per block element, which feeds the chunker's line-fallback path.
- `looks_like_html(payload)`: sniff the first 1024 chars (lstripped, lowercased) for a leading `<!doctype html` or a contained `<html`.
- `normalize_fetched_text(payload)`: sniff, then route to `html_to_text` or `normalize_text`.
  The sniff exists so angle-bracket source snippets (`list<T>`) in plain-text files are never eaten by the tag parser; it is a documented heuristic prior.

Why purity matters: the registry pins text by content hash, so normalization must be a pure function for hash-idempotent re-ingest.

### 1.6 Typed errors and the fail-fast policy

All retrieval errors derive from the project's single base error class (axiom: no raw exceptions cross region boundaries).

| Error | Carries | Raised when |
|---|---|---|
| `CorpusContentHashMismatchError` | doc_id, expected, actual | register with text that does not hash to the pin; OR read of corrupted stored text |
| `CorpusDocumentConflictError` | doc_id | re-register of the same doc_id with different content/metadata |
| `UnknownCorpusDocumentError` | missing doc_ids | snapshot creation or snapshot chunking over unresolvable members |
| `EmptySnapshotError` | - | snapshot over an empty member list |
| `Fts5UnavailableError` | - | index CONSTRUCTION when the linked SQLite lacks FTS5 |
| `SnapshotNotIndexedError` | snapshot_id | search/list over an unbuilt snapshot |

`Fts5UnavailableError` policy: raised at index construction (a cheap in-memory `CREATE VIRTUAL TABLE ... USING fts5` probe), before any query can run, and NEVER caught to degrade.
Rationale, worth keeping verbatim in spirit: retrieval quality metrics are meaningless if some environment quietly served a different ranking; a silent fallback would fake the eval numbers.
CLI consumers let it surface to stderr and exit 1.

### 1.7 Ingest tool

A manifest-driven CLI; in Loop it is `ingest_corpus --manifest ... --db ... [--dry-run] [--max-fetches N] [--timeout S] [--min-doc-chars N] [--snapshot] [--chunk-target-chars N] [--chunk-overlap-chars N]`.
The fetcher, today's date, and the clock are injectable so the whole tool is testable with zero network.

Manifest shape: a version literal (e.g. `"corpus-manifest-v1"`), a comment, classifier host lists, and `sources`, each entry `{url, expected_type, track_tags (non-empty), license_note, title, published_date?, comment?}`.
`expected_type` is a CROSS-CHECK, never an input: a deterministic URL classifier computes the real `source_type`, and a mismatch is printed loudly (`[type-mismatch]`) while the classifier wins.
A repo test validates the checked-in manifest against the classifier so the two can never drift.

Fetch policy:

- Only `http`/`https` URLs with a netloc; anything else (including `file://`) fails without being opened.
- robots.txt respected via the stdlib parser, fetched once per host and cached for the run; an unreachable robots.txt is read as allow (the conventional reading); a disallowed page is never opened.
- One request per manifest URL, no crawling, no link-following; curation lives in the reviewed manifest, not crawler heuristics.
- Per-request timeout (default 20 s), NO retries, and a per-run fetch cap (default 100) as the blast-radius bound.
- Important: there is NO sleep-based rate limiting in Loop's tool; politeness = cap + timeout + no retries.
- Response body decoded with the declared charset or UTF-8 with replacement; fixed user agent.

Registration flow per source, failures never stopping the run: classify; cap check (over-cap = skipped, NOT a failure); fetch; normalize with `normalize_fetched_text`; thin gate (`len(text) < min_doc_chars`, default 200, 0 disables); build the `CorpusDocument` with `doc_id = derive_doc_id(url, today)` and `content_hash = content_hash_for(normalized_text)`; register.
Status taxonomy: `registered, unchanged, conflict, fetch_failed, robots_disallowed, skipped_over_cap, skipped_thin`; the failure set (non-zero exit) is `{conflict, fetch_failed, robots_disallowed, skipped_thin}`.

Why the thin gate: a JS-rendered shell page would plant a permanently EMPTY document in the append-only registry (Loop's v1 corpus carries exactly one 0-char document as the cautionary example).

Idempotency semantics: same URL + same day + unchanged bytes = same doc_id + same hash = no-op (`unchanged`, exit 0); same URL + same day + CHANGED bytes = same doc_id + different hash = typed conflict, exit 1 (the operator re-fetches on a new day, which yields a new doc_id).

`--dry-run` prints one would-fetch line per source (derived doc_id, classified type, tracks, mismatch and over-cap annotations) and touches neither the network nor the database (it returns before the registry is even constructed).
`--snapshot` after a live run pins ALL registered documents into one snapshot under the flag-specified chunking params and prints the id.

Tests that pin it: no-op re-ingest; typed same-day conflict; fetch failures do not stop the run; thin skip fails the run; cap skips the remainder without failing; classifier-wins-with-loud-mismatch; dry-run isolation; robots respected and fetched once per host; repo-manifest consistency tests.

### 1.8 Retrieval eval harness

Evalset JSON shape:

```json
{"query_set_version": "retrieval-queries-v2",
 "comment": "…dropped drafts with reasons…",
 "cases": [{"query_id": "rq_swe_system_design_prep",
            "query_text": "how to prepare for a system design interview",
            "track": "swe",
            "relevant_source_urls": ["https://…"],
            "notes": "Judged 2026-07-06: …"}]}
```

`query_id` pattern `^rq_[a-z0-9_]+$`; duplicate ids and duplicate URLs are contract-rejected; query sets are append-only across versions (v1 is a verbatim subset of v2).

Labels are source URLs, not doc_ids, because doc_id embeds the collection date; URLs are the stable, human-auditable name, resolved against the pinned snapshot's membership at eval time.
Relevance is DOC-level: a chunk hit counts if its parent document is labeled relevant (chunk-level labeling was judged not worth the cost).

Metrics (pure functions, hand-computed values in tests):

- Collapse the chunk ranking to a doc ranking by first occurrence.
- `recall@k` = |top-k docs ∩ relevant| / |relevant|; an empty relevant set is a typed error (undefined), never a silent zero.
- `reciprocal_rank` = 1/rank of the first relevant doc, 0.0 on a total miss.
- Binary-gain `nDCG@k` = DCG over top-k hits (gain 1/log2(pos+1)) divided by the ideal DCG (`min(|relevant|, k)` positions).
- All values rounded to 4 places for stable serialization; report carries per-case and mean values plus the snapshot id and k.

A label URL absent from the snapshot is a typed error: a label that silently matched nothing would fake a zero into recall.
The searcher is a small Protocol (`search(query, *, snapshot_id)`), so retriever variants are graded by the same code over the same labels (the ablation seam).

Runner: takes `--queries --db --snapshot --k` plus `--strict` with three floor flags that must be given together; it rebuilds the FTS index idempotently before grading (the index is derived data); breaches print `FLOOR BREACH` lines to stderr and only `--strict` turns them into exit 1.
Floors are the values MEASURED on a pinned run, recorded with provenance comments, and re-measured (honestly, including drops) when the corpus grows.
One test deliberately breaks a floor and asserts the gate fails: the harness-can-fail proof.

### Starmap deltas (RAG)

- Drop entirely: embeddings, the vector cache, hybrid/RRF fusion, the source_claims layer, and track tags (single shared corpus; delete the `track_tags` column and filters).
- Keep the registry + snapshot + chunking + per-snapshot FTS design intact but smaller: one registry, likely exactly one live snapshot per catalog build.
  Keep the snapshot pin anyway; it is cheap and it is what makes the retrieval eval reproducible.
- Corpus documents = one per course (title + description + prereq prose + fulfills notes) and one per requirement group, generated by the catalog build; there is no web manifest, because the catalog build IS the ingest (fetch policy concerns move to the bulletin fetcher).
  Starmap's planned 1 req/s politeness is NEW code; do not assume the reference has a rate limiter to copy.
- Keep verbatim in spirit: the single hash definition, derived ids with short hex prefixes, append-only registry with typed conflict, hash-check on register and read, normalization purity, chunk-id derivation, match-expression quoting, `-bm25` ordering with chunk-id tie-break, FTS5 fail-fast at construction, and the eval harness with a small hand-labeled query set plus measured floors.
- Since course descriptions are short, most documents will be single-chunk; consider `target_chars` around 1200-1600 and overlap 0-200, still labeled heuristic priors.

---

## 2. Pathway / knowledge map

Ref: `contracts/pathway_template.py`, `contracts/knowledge_map.py`, `narrative/` (`coverage.py`, `generation.py`, `account_map.py`, `mastery.py`), `templates/pathways.py`, `templates/knowledge_maps.py`, `frontend/src/lib/atlas/layout.ts` (+ tests), `frontend/src/components/Observatory.tsx`, `NodeDrawer.tsx`, `frontend/src/lib/knowledgeMap.ts`.

### 2.1 The two-level groups/nodes model (no edges)

`PathwayTemplate` (frozen, extra=forbid): `pathway_id`, `pathway_schema_version`, `career_track` (closed enum), `display_name`, `spine`, `audience_note`, `evidence_slots` (non-empty, unique slot_ids), `knowledge_map` (nullable; attached at registry import, null keeps older fixtures valid).
`EvidenceSlot`: `slot_id`, `title`, `required_kinds` (non-empty closed-enum list, unique), `required_themes_any` (non-empty, case-insensitively unique), `min_items` (default 1, 1..10), `gap_module_hint`, `branch_skill_ids` (non-empty, unique; these seed the map generator).

`KnowledgeMap` is exactly two lists, `groups` and `nodes`, both non-empty.
Id patterns: groups `^kg-[a-z0-9-]+$`, nodes `^kn-[a-z0-9-]+$`.

`KnowledgeGroup`: `group_id`, `title`, `branch` (the evidence slot_id the group serves, or the literal `core` when 2+ slots seed it), `blurb`, `member_node_ids` (non-empty, unique).

`KnowledgeNode`: `node_id`, `title`, `kind` (closed 2-member enum: `skill` | `capstone`), plus six nullable fields (`skill_id`, `group_id`, `expected_minutes` (> 0), `evidence_slot_id`, `branch`, `blurb`).

Kind-conditional validation, one model validator:

- `skill` REQUIRES `skill_id`, `group_id`, `expected_minutes`; FORBIDS `evidence_slot_id`, `branch`.
- `capstone` REQUIRES `evidence_slot_id`, `branch`; FORBIDS `skill_id`, `group_id`, `expected_minutes`.
- Error messages name the node and list the missing/forbidden field names; invalid fixtures assert those substrings.

Map-level validators: group and node id uniqueness (distinct messages); BOTH-WAY membership (every skill node's `group_id` resolves to a group that lists it; every group member id resolves to a skill node whose `group_id` points back; four distinct error messages); at most one capstone per evidence slot.

There are NO edges: membership is a function, so cycle handling does not exist ("deleted, not deferred").
This is pinned by an executable test asserting the `edges` key is not in the model's fields.
The map is a presentation/memory layer only; it never gates any planner or scheduler behavior.

Example shapes:

```json
{"group_id": "kg-cs-foundations", "title": "CS Foundations", "branch": "core",
 "blurb": "…", "member_node_ids": ["kn-algorithms", "kn-data-structures"]}

{"node_id": "kn-algorithms", "title": "Algorithms", "kind": "skill",
 "skill_id": "skill.algorithms", "group_id": "kg-cs-foundations",
 "expected_minutes": 600, "blurb": "…", "evidence_slot_id": null, "branch": null}

{"node_id": "kn-llm-feature-depth-capstone", "title": "LLM feature shipped …",
 "kind": "capstone", "evidence_slot_id": "llm-feature-depth",
 "branch": "llm-feature-depth", "skill_id": null, "group_id": null,
 "expected_minutes": null, "blurb": null}
```

### 2.2 Slot-coverage kernel

Pure functions from `(UserProfile, PathwayTemplate)`; a leaf kernel depending only on contracts.

Outputs: per-slot `SlotCoverage {slot_id, state: filled|partial|empty, matched_item_indices}` (positional indices into the profile's experience list, avoiding an invented item id) and `PathwayFit {pathway_id, filled_slots, total_slots}`.

Algorithm (one pass):

1. Build the slot-id set and the override map from the profile's selection.
   Overrides apply only when the selection targets THIS template, so coverage computed for other pathways (card ranking) never picks them up; an override naming a slot the template lacks is filtered out here (the service layer rejects it with a typed code) so the kernel stays total.
   Override identity is the case-insensitive `(item_title, item_organization or "")` pair.
2. For each experience item in profile order: if an override forces a slot, assign and continue (overrides bypass kind/theme checks entirely); otherwise scan slots in TEMPLATE order and assign to the first slot where the item's `kind` is in `required_kinds` AND the casefolded theme sets intersect, then stop.
   This realizes "one item fills at most one slot; tie-break by slot order then item order".
3. State per slot: `count >= min_items` = filled; `count >= 1` = partial; else empty.

`pathway_fit` counts filled slots; it is a card-ordering KEY (sort by filled descending, ties by registry order), never a score.
Theme comparison uses the same shared casefold helper the contracts use, so `"Applied-ML"` and `"applied-ml"` always join.

Tests pin: first-match-by-template-order, item-order preservation in indices, min_items transitions, kind mismatch, case-insensitive theme join, override precedence and its edge cases (other-pathway selection ignored, unknown slot ignored, forced assignment without a kind/theme match), and two-call determinism.

### 2.3 Map generation and the vocabulary gate

`generate_map(template, grouping, taxonomy, *, ceiling=40) -> KnowledgeMap`, a build-time pure function (a CLI writes the committed JSON artifact; nothing generates a map at runtime).
Failures are a typed `MapGenerationError(reason_code, detail)`, never silent placement or pruning.

Steps:

1. Resolve each slot's `branch_skill_ids` seeds through the curated skill-grouping table, recording which slots seed each group (`seeded_by: group_id -> set[slot_id]`).
   Empty seeds and unrowed seeds are distinct typed failures.
2. Every included group brings ALL its member skills.
3. Build one skill node per member (members sorted by `skill_id`), title from the pinned taxonomy display name; a grouping row that does not resolve against the taxonomy is a typed failure naming the taxonomy version.
   `node_id_for(skill_id) = "kn-" + skill_id.removeprefix("skill.")` is the single source of truth for skill-node ids; the runtime addition path reuses it so an added skill lands on the same id the generator would have used.
4. Budget check: more skill nodes than the ceiling is a loud typed failure (`trim seeds or split oversized groups`), never silent pruning.
   A too-thin map (< 20 skill nodes) is advisory only (log, never fail).
5. Branch per group: the single seeding slot's id, or `core` when 2+ slots seed it.
6. One capstone per slot: `node_id = "kn-" + slot_id + "-capstone"`, title = slot title, branch = slot id.
7. Canonical ordering for byte-stable output: groups sorted (core first, then slot order, then group_id); skill nodes by `(group_id, skill_id)`; capstones by slot order; nodes emitted as skills then capstones.
   Same inputs always produce an equal map with byte-identical serialization (no timestamps anywhere).

THE key pattern - the vocabulary gate: one pure projection, `pathway_node_vocabulary(generated_map, *, additions, display_names) -> ordered list[(node_id, title)]`, produces the node vocabulary that BOTH (a) goes into the LLM prompt's constraints (the model is told to tag only ids from this list) and (b) is handed to the deterministic validator that rejects any tag outside it with a typed `UNKNOWN_KNOWLEDGE_NODE` violation.
The composition root passes the SAME object to both consumers, not a re-derivation, so prompt and gate can never drift.
Projection details: the generated map's skill nodes in committed order, then additions not already present sorted by node_id (total order = byte-stable), titles from the pinned taxonomy for additions; capstones are excluded (not training targets); personal/custom content never enters (the injection wall).
The same pattern repeats for slots and mastery bounds: the gate always disposes exactly what the prompt was told.

`merge_additions(generated_map, additions, *, grouping, taxonomy)` places each user-added skill into the group its grouping row names (the user picks WHAT, code decides WHERE), creating a missing group with branch `core` and one member; already-present/unrowed/undisplayable additions are skipped defensively (the write API rejects them at write time); the result is re-run through full `KnowledgeMap` validation so every invariant re-holds.

Tests pin: per-pathway double-generation equality AND byte-identical JSON; exactly one capstone per slot; the ceiling; node-id derivation; canonical ordering; core-branch assignment for multi-slot groups; the three typed failure codes; vocabulary ordering and dedupe; merge round-trips through validation.

### 2.4 Registry pattern and the committed artifact

Templates are module-level validated constructor calls (not dicts), so they are contract-checked at import; the registry is an immutable mapping (`MappingProxyType`) keyed by `pathway_id`, built in declaration order.
Two version strings: a per-template SCHEMA version and a registry CONTENT version; a user's stored selection pins the content version, so an append-only registry bump never silently re-maps a live selection (a mismatch is a typed rejection telling the user to re-confirm).

Generated maps live in a committed JSON artifact (top-level: `maps` keyed by pathway id, plus the registry/grouping/taxonomy version pins).
A build tool writes it; its `--check` mode byte-compares regeneration against the committed file and fails CI on drift ("run make maps and commit").
The loader validates through the contract, caches with an lru_cache of size 1 (import never triggers file I/O), and grafts the map onto a template via full re-validation (house rule: never a bare `model_copy(update=...)`).

Registry tests pin: unique ids, round-trips, version pins, every theme referenced by a slot being in the track's closed theme vocabulary, every seed skill resolving against the pinned taxonomy, and a text-field denylist (no prestige terms).

### 2.5 Deterministic layout kernel (the atlas)

React-free TypeScript module; the map carries no coordinates, so the sky is computed, and computed identically on every render.

Canonical space: `CANONICAL_VIEWPORT = {w: 1180, h: 665}`; all math runs in it; a caller may pass a same-aspect viewport to receive pre-scaled coordinates (`sx = w/1180`, `sy = h/665`).

Signature and output:

```ts
layoutSky(view, viewport = CANONICAL_VIEWPORT, openGroups = new Set())
  -> PositionedSky {
       regions: {branch, cx, cy, rx, ry, grad, labelX, labelY}[]
       capstones: {nodeId, branch, x, y}[]
       systems: {groupId, x, y}[]
       personalHeader: {x, y} | null
       usedGridFallback: boolean
       planetsFor(groupId): {nodeId, x, y, angle}[]
     }
```

Determinism mechanism - there is NO PRNG in the layout kernel.
Determinism comes from: analytic seeding, fixed anchor tables, a fixed iteration count, a deterministic tie-break for coincident bodies, and final rounding.
(The only seeded PRNG in the atlas is a Lehmer generator in the decorative background dust layer, a sibling module; do not confuse the two.)

Fixed pieces:

- Region anchors: a lookup table keyed by the non-core branch count `n` (n=1 centered; n=2 left/right; n=3 a hand-tuned hero triangle; n=4 quadrants; n>=5 a computed ring around the center).
  A core anchor sits lower-center (dead-center when n>=5); a personal-layer anchor sits bottom-right.
  Anchors are NEVER relaxed; only bodies inside move, so clusters stay stable and legible.
- Seeding: system bodies seed on a golden-angle spiral around their cluster anchor (`r = SEED_R * sqrt(clusterIndex + 0.5)`, `angle = clusterIndex * GOLDEN` with `GOLDEN = pi*(3 - sqrt(5))`, `SEED_R = 34`), spring target = the anchor center.
  Capstone bodies seed at (and spring to) the region "head" (`cx`, `cy - ry*0.62`, clamped).
  Seed recipes are computed ONCE so the first pass and any re-seed are byte-identical.
- Canonical ordering: branches keep the view's order; groups are sorted by `group_id` WITHIN each partition (branch groups, core groups, personal groups), so the seed walk depends on ids, not input array order.

The force model (`relax(bodies, kRep)`, exactly `ITER = 300` fixed iterations):

- Pairwise repulsion between all bodies: `f = kRep / (d^2 + REP_SOFT)`, skipped beyond `REP_CUTOFF = 300`; a coincident pair (`d^2 < 0.0001`) gets a deterministic index-based nudge (`dx = (i-j)*0.1, dy = 0.1`), which is where a naive sim would reach for randomness.
- A spring to the fixed anchor: `f += K_SPRING * (target - pos)` with `K_SPRING = 0.04`.
- Integration with per-axis force magnitude clamped to `MAX_STEP = 20`, then position clamped into the rim (`RIM_PAD = 40` inset).
- Constants: `K_REP = 30000`, `REP_SOFT = 60`, unit step.

Overlap policy (bounded, never open-loop): after relaxing, check all system pairs against `SYS_MIN_SEP = 96`.
If unmet, re-seed from the SAME recipes and re-run once with `K_REP * 1.7`.
If still unmet, place systems on an even grid inside the rim (`cols = ceil(sqrt(n))`), set `usedGridFallback = true`, and emit a loud console warning - never a scrambled sky, never a silent crop.

Planets are NOT simulated: collapsed groups return every member at the star center with angle 0; open groups place members analytically, evenly spaced on a fixed `ORBIT_R = 64` ring starting at -90 degrees (even spacing provably separates for the <= 8-member budget).
Star, capstone, and region positions are open-independent, so the sky never reshuffles on expand.

Every emitted coordinate passes `round1(v) = Math.round(v*10)/10`, absorbing float drift so output is exactly reproducible.

Test strategy (the part worth copying wholesale):

- Purity: two independent calls on the same view deep-equal.
- Byte-stability: an inline snapshot of the reference map's exact one-decimal coordinates (the regression guard against accidental jitter).
- Composition fidelity: every system satisfies the ellipse-containment inequality for its seeded region; a couple of relative-position assertions.
- Shape sweep: ~24 synthetic cases (branch count x member count) each asserting no fallback fired, minimum pairwise separation >= 96, everything inside the rim, one position per group - this is the empirical convergence bound on ITER.
- Order stability: reversing the input groups and nodes arrays changes no coordinate.
- Collapsed vs open planet behavior; degenerate empty view; a 60-group over-budget view triggers the grid fallback with all positions in-rim; viewport scaling halves coordinates for a half-size viewport.

### 2.6 Thin components over the pure lib

The screen owns SERVER state (the fetched map view, selection, busy, error, a `resetKey` counter); the atlas component owns only VIEW state (open groups, focus target, hover, panel, a measured container width).
The layout call is memoized on `(view, openGroups)` so hover renders never re-run the sim.

Interaction model worth reusing: click a star toggles the group open and focuses it; click a node selects it (opens a detail drawer) and focuses its system so it glides clear of the drawer; click empty sky resets the view (child buttons stop propagation so only background clicks reach it); a backdrop click dismisses the drawer AND resets the view via the `resetKey` bump, while the close button and Esc leave the sky as-is.

Drawer accessibility contract: `role="dialog" aria-modal="true"` over a backdrop; on mount capture the previously focused element and focus the close button; Esc closes; Tab is trapped (wrap last-to-first and first-to-last on Shift+Tab over the focusable query); cleanup restores focus to the invoking element.
The focus effect runs mount-only and reads the close callback through a ref, so a fresh closure never re-runs it and steals focus mid-typing.
Drawer draft state (e.g. a note textarea) is re-seeded by an effect keyed on the node id, so switching nodes never leaks the previous draft.
Every mutation awaits the server's refreshed view; derived values (tiers, counts) are recomputed server-side, never client-side.

There are deliberately NO component tests: all logic lives in the React-free, vitest-covered lib modules, and the components are thin renderers over those descriptors.
Every optional per-node signal is read through one coalescing reader that defaults absent fields to null/false, so partial payloads degrade gracefully; each visual flourish is data-gated (absent data = omitted ornament, never a fabricated one).

### 2.7 View-model lib

A React-free projection module over the server view: label helpers, honest `n/m` count labels (never percentages), group partitioning where the core partition is defined NEGATIVELY (not personal and not under any rendered branch) so no group can ever be dropped by an unexpected branch value, member resolution in declared order with defensive filtering, and mirrors of server gates (which tiers are user-settable; which nodes accept an action) so the UI disables what the server would reject.

### Starmap deltas (pathway map) - including the flagged design change

Starmap ADDS two things this map deliberately lacks: semester ordering and prerequisite edges.
That changes the design as follows:

- Nodes carry `semester_index`, so START with a semester-column layout: columns = semesters, deterministic row packing within a column (sort by a stable key such as course code, fixed row pitch, center vertically).
  It is trivially deterministic, needs no force sim, no separation check, and no fallback.
  If a constellation look is wanted later, timebox a force upgrade and keep this section's recipe: analytic seeding, fixed anchors per column, fixed ITER, deterministic coincidence nudge, bounded second pass, loud grid fallback.
- Prereq edges become real rendered edges, but their DATA is deterministic catalog data derived from the validated prereq expression trees - never LLM output.
  Because edges now exist, cycle handling exists too, but only as BUILD-TIME catalog validation: detect cycles during the catalog build, report them in the parse report, and break/flag them there, so the frontend can still assume a DAG.
- Keep: the no-PRNG determinism discipline, the canonical fixed viewport, `round1` final rounding, order-stability (sort by ids before layout), the byte-stable inline-snapshot + purity + order-stability test trio, and the thin-view-over-pure-lib split with no component tests.
- Keep the drawer contract wholesale (focus trap, Esc, restore focus, backdrop-dismiss vs close distinction, draft re-seed by node id).
- Drop: mastery tiers, overlays/additions/personal content, capstones, evidence slots, groups (Starmap's grouping axis is the pathway tab + semester column; department or requirement-group could color nodes instead), and all account-map merging.
- Keep the vocabulary-gate pattern in its Starmap form: the candidate course pool that goes into the proposer prompt IS the list the validator checks `unknown_course` against - one projection, two consumers, same object.
- Keep the coverage-kernel SHAPE for the "covers N of M core groups" badge: a pure function from (validated pathway, curated requirement groups) to filled/partial/empty counts, greedy first-match, count not score.
- Keep the committed-artifact + regenerate-and-byte-compare `--check` pattern for anything built (catalog-derived JSON, curated requirements).

---

## 3. Onboarding

Ref: `frontend/src/lib/intake.ts` (+ `intake.test.ts`), `frontend/src/screens/Onboarding.tsx`, `app/web/routes_cycle.py` (onboard handlers), `app/cycle.py` (`onboard`, `extract_resume`), `contracts/user_profile.py`, `llm_nodes/resume_intake.py`.

### 3.1 The React-free wizard-state module

All wizard logic lives in one React-free module; the screen is a thin view.
The stated split: the server-side profile contract is the validation oracle, and any LLM proposal only ever lands in client state the user can edit; nothing persists until the wizard finishes through one POST.

Core exports (Loop's surface, for shape):

```
STEP_LABELS: string[]                     // the step titles, index = step
stepFromParam(raw: string | null): number // ?step= deep link -> clamped index
initialForm(me): FormState                // server profile -> form (prefill)
buildPayload(form, timezone): Payload     // form -> POST body
cleanList(items): string[]                // trim, drop blanks, casefold-dedupe
addChips(list, raw): string[]             // comma-splitting chip append
extractDisabled(text, pending): boolean   // client mirror of contract bounds
sectionsHaveContent(form): boolean        // confirm-gate predicate
applyProposal(form, result): FormState    // replace-on-extract
failureNotice(result): {code, detail} | null
```

State shape: FLAT and string-biased - `''` stands in for the contract's null because controlled inputs want strings; compound contract structures are flattened (e.g. a list of day-windows becomes selected-days + one shared start/end pair) and reconstituted in `buildPayload`.

Deep-link policy (`stepFromParam`): parse int with junk-to-0; clamp negatives to 0 and out-of-range to the LAST step, so a stale link can never open a step that no longer exists.
When inserting a step, keep earlier indices stable so existing deep links still land; a cross-module test pins the mapping (the module that generates reason-code deep links is imported by the wizard test and asserted against `STEP_LABELS`).

`buildPayload` rules:

- `user_id: 'pending'` - the server ALWAYS overwrites it with the session user (the trust boundary; never trust a client-supplied user id).
- Trimmed-empty optional strings map to null, never `''`, because the contracts reject empty strings by design (min_length=1).
- List fields go through `cleanList` (trim, drop blanks, case-insensitive dedupe with first spelling winning) because the contracts require case-insensitive uniqueness.
- Rows without a title are empty editor rows, not entries - dropped.
- Compound objects are emitted only when complete (e.g. a selection needs both the id and its pinned registry version; a bare id would be contract-invalid), else null.
- Timestamps are client-stamped ISO strings; the server re-stamps with its own clock.

`initialForm` prefill: every field defaults with `??`; a NEW user gets useful defaults (e.g. weekday windows pre-selected so a click-through onboard produces something usable) while an EXISTING profile keeps exactly what it saved, even empty.
A sentinel server default (Loop: timezone `'UTC'`) is treated as UNSET and re-detected from the browser, because it is a fallback no user picks.

### 3.2 Extract-merge policy (who wins)

Loop's resume-extraction merge policy, worth copying for any auto-fill Starmap adds later:

- REPLACE, not merge: applying a proposal replaces exactly the enumerated auto-fillable sections (five in Loop) and touches nothing else (spread the old form first, overwrite those keys).
- Confirm gate: if ANY of those sections currently holds user-visible content, the proposal is held in pending state and applied only on an explicit confirm - never destroy hand-typed input silently.
  An empty editor row alone is not content.
- Canonical over raw: extracted skill surfaces are stored under their taxonomy-resolved canonical display names; unmatched surfaces stay OUT of the form until the user explicitly keeps them.
- Failure is inert: a non-ok result makes `applyProposal` return the IDENTICAL form object reference (===), so failure literally cannot mutate state; `failureNotice` turns it into a typed banner (`reason_code` with a client-side fallback code for a malformed body).
- Honest labeling: inferred sections carry an "inferred" label only while at least one extracted entry survives user editing (case-insensitive set intersection).

### 3.3 The persistence-free LLM extraction endpoint

The HTTP status-code policy, stated once and applied everywhere:

- A WORKFLOW failure (the LLM call failed, validation rejected the output) is a normal result: HTTP 200 with `status: "failed"` and a typed `reason_code` in the body.
  Rationale: extraction failure is a local, retryable UX event, not a server error and not a run failure; the client shows a banner and every field stays hand-editable.
- A contract-invalid REQUEST (text too short/long, malformed shapes) is the standard 422 via a global `ValidationError` handler.
- A command-precondition failure (acting on missing state) is 409.

Endpoint mechanics (POST, body `{resume_text, draft_context?}`):

1. First validation pass pins the input contract with `user_id` FORCED to the session user and any client-supplied vocabulary blanked - so step 2 reads typed data, not raw client JSON.
   Invalid payloads raise here, BEFORE any LLM call.
2. Server-side vocabulary injection: re-validate the same bundle with the allowed vocabularies (taxonomy slice, theme vocabulary) filled from server registries - registry literals, never client input; the LLM node never imports the registries.
3. Mint a prefixed run id (`intake-<id>`) marking a pre-run call in the LLM call log; no run/checkpoint state is created.
4. Run the node inside try/except; on the typed node error return the 200 failure result carrying `reason_code` (falling back to a generic code when untyped).
5. On success, deterministically post-process (Loop: resolve skill surfaces against the taxonomy; matched ones dedupe by skill id with first surface winning; unmatched returned visibly flagged, never silently promoted).
6. Return the result.
   NOTHING is persisted anywhere in this path; the only profile write path is the onboard POST.

The response envelope is serialized with `model_dump(mode="json")` into a plain JSONResponse (no framework response-model coercion), so the API body is byte-identical to the operator/CLI surface.

### 3.4 The onboard endpoint

- Router takes a RAW dict body; the profile contract itself is the validator (validation happens once, in the service).
- Trust boundary: the client's `user_id` is always overwritten with the session user before validation.
- Service flow: validate the whole record (contract-invalid = 422); run SEMANTIC registry checks the contract cannot do (unknown pathway id, stale registry-version pin, override naming a missing slot) - a semantic rejection returns 200 with `status: "rejected"` + typed code and persists NOTHING; on re-onboard preserve the original `created_at` (and any fields onboarding never sets) by rebuilding the record through full validation; if a load-bearing choice changed (Loop: the selected pathway), run a deterministic invalidation of derived state; finally one single write.

### 3.5 The profile contract, with the Starmap keep/drop map

`UserProfile` (frozen, extra=forbid) fields, annotated:

| Field | Constraint | Starmap |
|---|---|---|
| `user_id`, `profile_version` | non-empty | keep (session-scoped) |
| `goal`, `target_role` | non-empty | keep (career direction) |
| `target_companies` | list, default [] | optional |
| `target_level` | nullable | drop or keep |
| `timeline_weeks` | int > 0 | becomes planning horizon (semesters) |
| `weekly_hours` | 0 < x <= 40 | drop (or coarse credit appetite) |
| `experience_level` | closed enum | analog: school year |
| `known_strengths`, `known_weaknesses` | lists | optional |
| `experience` | max 20 items | analog: completed courses |
| `skills` | max 40, each 1..60 chars, casefold-unique | analog: interests chips |
| `preferred_session_length_min`, `max_session_length_min` | 0 < x <= 720 | DROP (scheduler) |
| `deep_work_windows` | list of day+start+end | DROP (calendar) |
| `hard_constraints` | nested model, required | DROP (calendar) |
| `preferences` | nested model of booleans | DROP (scheduler) |
| `motivation_profile_id` | nullable | drop |
| `resume_text` | nullable, raw context | drop (no resume) |
| `plan_direction` | nullable, 1..4000 chars | analog: career free text |
| `pathway_selection` | nullable nested model | drop (Starmap generates per-request) |
| `created_at`, `updated_at` | tz-aware datetimes | keep |

Validator inventory (the pattern catalog to reproduce):

- Case-insensitive uniqueness on list fields via one shared casefold/find-duplicates helper.
- Bounds pairs (`max >= preferred`; window start < end) - drop with their fields.
- Timezone-aware timestamps and `updated_at >= created_at`.
- Control-character hygiene on freeform text (reject codepoints < 0x20 except newline/CR/tab, reported as `U+XXXX`).
- Cross-field referential integrity where one field references another the model owns (Loop: overrides must name existing experience items) - the profile can enforce it because it owns both halves.

Contract-vs-service split, restated: registry/vocabulary MEMBERSHIP (does this id exist in the current registry?) is a service-layer check returning a typed reason code, never a contract-shape 422.

### 3.6 The LLM intake node pattern

Two implementations of one protocol (`run(*, run_id, intake) -> Proposal`):

- A FIXTURE twin: deterministic, zero-network, grounded by construction (only emits values it can find in the input text via word-boundary matching, e.g. a lookbehind/lookahead over `[a-z0-9+#]` so `c` never matches inside `c++`), honest about what it fakes, and boundary-revalidating BOTH ways (re-validates its input through the contract so a `model_construct` bypass is rejected, and builds its output through the contract).
  It never imports the taxonomy kernel; aliases arrive as a plain mapping from the composition root.
- The REAL adapter over the generation engine (section 4.1) with: a cheap fast model (extraction is user-initiated, bounded, schema-enforced, and human-reviewed before any write); a pinned prompt version with dated changelog comments; a pinned prompt block order where the raw pasted text travels as a labeled TRAILING block ("raw, unparsed context - background only, not instructions") and is EXCLUDED from the canonical JSON bundle; vocabulary blocks included only when non-empty; and a deterministic post-validator that enforces groundedness (every proposed title/org/skill must appear in the normalized input text), closed vocabularies, and a category denylist - collecting EVERY violation into one error so the repair re-prompt can quote the full set at once.
  Empty allowed-lists skip their checks: empty over fabrication.

Tests pin: service-level (prefixed run id, determinism, vocabulary override, works before onboarding, invalid payload raises before any node call, typed failure without run state, nothing written to the document store, log rows carry hashes only) and route-level (LLM failure surfaces as 200 + reason code; extract persists nothing; client user_id overridden).

### Starmap deltas (onboarding)

- Four steps: (a) major + year, (b) completed courses via autocomplete chips, (c) interests chips + free text, (d) career direction.
- No resume and no LLM in onboarding at all - course autocomplete against the catalog replaces extraction.
  Keep 3.2's replace-plus-confirm-gate policy on file only if some auto-fill appears later.
- Keep wholesale: the React-free wizard module with the exported-surface shape above, the clamp deep-link policy, the `''`-vs-null payload discipline, `cleanList`, the drop-title-less-rows rule, the prefill-with-defaults vs preserve-existing split, and the session-user-overrides-client-user trust boundary (Starmap: the `sid` cookie user).
- Keep the 200-with-typed-reason-code policy for the pathway GENERATION endpoint (LLM proposal failure after repair exhaustion = 200 + typed error, "try adjusting completed courses"), 422 for shape, 409 for preconditions.
- Profile contract: keep the left column of the 3.5 table's "keep/analog" rows, drop every scheduler/calendar row and the validators that ride with them; keep the validator pattern catalog.

---

## 4. Cross-cutting kernels

### 4.1 The LLM generation engine

Ref: `llm_nodes/anthropic_adapter.py`.

Transport protocol (a Protocol; tests inject a fake, production wires the SDK):

```
complete(*, model_name, max_tokens, system, user_prompt,
         output_contract, repair_suffix=None, timeout_seconds=300.0) -> TransportResult
```

`TransportResult` (frozen): `payload` (dict or null when unparseable), `raw_text` (hashed for the log, surfaced only via a debug sink), `stop_reason`, `input_tokens`, `output_tokens`, `cache_creation_tokens` (default 0), `cache_read_tokens` (default 0).
Cache tokens are excluded from `input_tokens` by the provider and priced at 1.25x (write) / 0.10x (read) of the base input rate.

`TransportError(message, *, retryable=True, reason_code=None)`: `retryable` discriminates transient provider weather (rate limit, overload, connection blip, timeout) from permanent rejections (bad credentials, malformed request - retrying is pure noise).
Error messages carry the SDK exception TYPE NAME only, never bodies (bodies may quote request content or credentials).
Translation table: auth/permission errors = non-retryable + auth code; rate limit = retryable + rate-limit code; bad-request/not-found/unprocessable = non-retryable + generic call-failed code; everything else (529, 5xx, connection, timeout) = retryable + call-failed code.

Two critical production-transport decisions:

- The transport requests schema-shaped output (the provider's json_schema output format) but returns the RAW model JSON, never a validated object: eager SDK-side validation would raise a `ValidationError` INSIDE the SDK call and escape the bounded repair loop.
  The engine re-validates the raw dict and owns repair.
  Corollary: schema-enforced output must STILL be boundary-revalidated - a payload can parse and satisfy the wire schema yet violate cross-field contract invariants (a test constructs exactly that case).
- Extended thinking is explicitly pinned OFF: on some model tiers, omitting the parameter silently enables adaptive thinking whose tokens bill inside `max_tokens`, which would truncate small-cap prose calls.
  Sampling parameters are deliberately not configured (several tiers reject them); output comparability rests on prompt-byte pinning instead (4.6).

`AdapterConfig` (frozen): `model_name`, `prompt_version`, `max_tokens`, `input_price_per_mtok`, `output_price_per_mtok`, `max_sdk_retries` (default 2, contract-capped `0 <= x <= 2`), `max_repair_attempts` (default 2, contract-capped `0 <= x <= 2`), `timeout_seconds` (default 300), `retry_backoff_seconds` (default 1.0).
The caps live in the FIELD CONSTRAINTS, so a config exceeding the bound fails validation rather than being clamped.
Cost estimate: `((input + 1.25*cache_write + 0.10*cache_read) * in_price + output * out_price) / 1e6`, labeled an estimate, not a billing fact.

The engine: constructed per node with `(node_name, output_contract, config, transport, call_log_store, clock, id_generator, debug_raw_sink?, sleeper?, attempt_recorder?)`.
The sleeper is injected so tests never really sleep; the attempt recorder is an observability hook that never influences generation.

Outer loop, `generate(*, run_id, plan_version, system, user_prompt, post_validate=None)`:

```
repair_context = None
for attempt in 0 .. max_repair_attempts:          # <= 3 iterations
    repair_suffix = None if repair_context is None else
        "\n\nYour previous output was rejected by deterministic validation. " +
        "Fix exactly these problems and return the corrected object:\n" + repair_context
    outcome = run_attempt(..., repair_suffix)
    if outcome is a validated model: return outcome
    repair_context = outcome                       # rejection text
raise typed REPAIR_LIMIT_EXCEEDED
```

The prompt-cache mechanism, exactly:

1. Violation feedback is never concatenated onto the user prompt; it travels as a SEPARATE `repair_suffix` string through a distinct transport kwarg, so `user_prompt` is byte-identical on every attempt (a test asserts `requests[1].user_prompt == requests[0].user_prompt`).
2. The transport renders one user message with two content blocks: the base prompt block carrying `cache_control: {type: "ephemeral"}`, then the suffix block (when present).
3. The cache breakpoint sits on the BASE PROMPT block, not on `system`: providers only cache prefixes above a per-model token minimum (thousands of tokens) which system prompts alone never reach; blocks below the minimum silently do not cache.
   Net effect: system + base prompt are served from cache on repair rounds; only the suffix is re-processed.
4. The logged `prompt_hash` is still sha256 over the FULL rendered bytes (`system + "\n" + prompt + (suffix or "")`) - the same bytes the model sees.

Inner loop, `run_attempt` (one repair attempt = up to `max_sdk_retries + 1` provider calls; every call appends exactly one log row):

| Outcome | Logged reason code | Behavior |
|---|---|---|
| transport error, non-retryable | its code or call-failed | log, raise typed error immediately (no backoff) |
| transport error, retryable, not last | its code or call-failed | log, sleep `backoff * 2^retry` (exponential, NO jitter - determinism beats thundering-herd at this scale), continue |
| transport error, retryable, last | retry-limit-exceeded | log, raise typed |
| stop_reason == refusal | refusal | log with refusal flag, raise typed - a refusal is never retried (same input, same answer) |
| payload null + truncated, not last | truncated | log, continue (transient) |
| payload null + truncated, last | retry-limit-exceeded | log, raise typed |
| payload null, not truncated | malformed-output | log, RETURN repair text listing the contract's required top-level keys (computed from the model's required fields) |
| contract or post_validate rejects | schema-rejected | log, RETURN the formatted violation text |
| success | none (outcome pass) | log, return the validated model |

Budgets compose: <= 3 repair attempts x <= 3 provider calls = worst case 9 calls, each logged.

Unified repair formatting (one renderer for all rejection channels, so repair quality is a property of the violations, not the path they took):

```
- field: {path} | constraint: {constraint} | offending value: {value}
```

For a pydantic error: path = dotted `loc` (or `(root)`), constraint = `{type}: {msg}`, value = the offending input CLIPPED at 120 chars with an explicit clip marker (model-level validators receive the whole object; clipping keeps the re-prompt guidance, not a second copy of the rejected output).
Post-validators may raise plain `ValueError`s (repairable) but must never raise the terminal generation error type.

### 4.2 The call log

Ref: `llm_nodes/call_log.py`, `llm_nodes/sqlite_call_log.py`.

One frozen record per provider call: `llm_call_log_id`, `run_id`, `plan_version` (nullable), `node` (a closed enum of the allowed LLM nodes - no other caller may log here), `prompt_version`, `model_name`, `attempt`, `sdk_retry`, the four token counters, `cost_estimate_usd`, `latency_ms` (measured across the transport call via the injected clock), `validation_outcome` (pass|fail), `reason_code` (nullable), `cache_hit` (= cache_read > 0), `truncated`, `refusal`, `prompt_hash` (nullable sha256 hex), `response_hash` (nullable sha256 hex), `created_at`.

Invariants: `created_at` tz-aware; `reason_code` non-null IFF outcome is fail (both directions); refusal implies fail; `truncated` deliberately unconstrained (a truncation that still parsed and validated stays pass; the flag preserves the provider's stop reason).

The record stores identifiers, counts, hashes, and outcome metadata ONLY - never raw prompts or responses; `extra="forbid"` makes a raw-content field structurally impossible.
A transport failure still logs a row (zero tokens); pinned by test.

Store: append-only (`append`, `list_for_run`, `list_all`); duplicate id is a typed already-exists error, enforced by an explicit SELECT inside the insert transaction (same discipline as 1.1).
SQLite sketch: `llm_call_logs(llm_call_log_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL)` plus an index on `run_id`; payload = canonical model JSON, reads re-validate.

### 4.3 The SQLite kernel

Ref: `common/sqlite.py` (about 140 lines, stdlib-only so every region can depend on it).

`SqliteDatabase(path)`:

- Connection: `check_same_thread=False`, `isolation_level=None` (autocommit, so transaction boundaries are ONLY the explicit BEGIN/COMMIT/ROLLBACK), `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`.
- One `threading.RLock` serializes every transaction and read, so two threads can never observe a torn write (which is what makes `check_same_thread=False` safe).
- `transaction()` context manager: acquire the lock, `BEGIN IMMEDIATE`, yield a cursor; commit on normal exit, rollback on ANY exception (so a store can write-then-check-then-raise), close the cursor in finally.
- `read()` context manager: a serialized read-only cursor in autocommit (no write lock taken).
- Transactions NEVER nest: a store method does all its SQL inside one block and never calls another method that opens its own transaction while one is active.
  Practical consequence seen in 1.4: read everything you need from other stores BEFORE opening your write transaction.

`ensure_schema(component, *, version, statements)`:

- A single `schema_version(component TEXT PRIMARY KEY, version INTEGER NOT NULL)` table, created if absent.
- Per component, inside ONE transaction: select the on-disk version; if present and different, raise a typed `SchemaVersionMismatchError(component, on_disk, expected)` - raised INSTEAD of migrating (no migration framework; fail loudly rather than guess); run all statements (each a single idempotent `CREATE TABLE IF NOT EXISTS` / `CREATE INDEX IF NOT EXISTS`); insert the version row if it was absent.
- Every store declares its own `(component, version, statements)` triple and calls this in its constructor.

### 4.4 FastAPI app assembly (SPA-mount ordering)

Ref: `app/web/app.py`.

`create_app` registration order, and why it matters:

1. Mode guards (hosted mode requires its auth pieces; dev mode requires a default user).
2. `app.state` wiring (environment, service, auth flags).
3. Session middleware + auth router (hosted only; cookie `same_site="lax"`).
4. Canonical-host redirect middleware, added AFTER the session middleware so it runs outermost (redirect before any session work); `/healthz` is exempt so machine probes never chase a redirect; 301 preserving path and query.
5. `GET /healthz`.
6. Exception handlers, most-specific first: domain precondition error = 409; domain base error = 400; `ValidationError` = 422; `ValueError` = 400.
   Trap to remember: pydantic's `ValidationError` IS a `ValueError` subclass; the more specific handler must exist or every 422 becomes a 400.
7. The API router (all `/api/*`).
8. Static public pages (`/`, marketing siblings, `robots.txt`, `sitemap.xml`, policy pages), each conditional on its file existing.
9. LAST: the SPA mount - a `/assets` static mount plus a `GET|HEAD /{path:path}` catch-all that serves a real top-level file when it exists (resolved and CONFINED to the dist dir - path-traversal check) and `index.html` otherwise.

Three reasons the ordering is load-bearing:

- The catch-all matches everything and routes resolve in registration order, so anything registered after it is unreachable.
- Recorded production incident: before a real `/privacy` page shipped, the catch-all answered that URL with the SPA shell and browsers CACHED it, client-redirecting `/privacy` into the app long after the real page went live.
  Fix: every HTML document is served with `Cache-Control: no-cache` (hashed `/assets` bundles exempt - their names change per build).
- The SPA is mounted only when a built `index.html` actually exists, so API-only test builds keep clean 404s on non-API paths.

Two more habits: public HTML routes accept HEAD alongside GET (a GET-only route answers HEAD with 405, which automated link checkers read as a dead page); error bodies are `{error, type, reason_code?}` built by one helper.

### 4.5 Contracts conventions

- Every contract model, nested models included: `model_config = ConfigDict(extra="forbid", frozen=True)`.
  `extra="forbid"` is used as a structural guarantee (e.g. it makes a raw-content log field or a confidence field impossible), not just hygiene.
- Updates rebuild through full validation: `Model.model_validate(record.model_dump() | updates)` - never a bare `model_copy(update=...)`, so every invariant re-runs.
- Cross-field checks are `@model_validator(mode="after")` returning self and raising `ValueError` with messages that NAME the field and QUOTE the offending values (the repair formatter and the fixture tests both depend on that).
  The pattern catalog is in 3.5.
- Shared helpers: one `_dedup` module providing `casefold_key` and `find_duplicates`, used by contracts AND kernels so joins and uniqueness agree everywhere.
- One spec doc per contract: each contract module's docstring names its canonical `docs/specs/<name>.schema.md`; the discipline is spec first, then model, then fixtures, then generated schema, then tests.
  Specs may carry normative tables that tests assert against directly.
- Generated JSON schemas: an explicit `CONTRACTS: dict[name, model]` registry; `model_json_schema(mode="serialization")`; files written as `json.dumps(schema, indent=2, sort_keys=True) + "\n"` (that exact recipe IS the byte-determinism mechanism); committed to the repo so drift is reviewable.
  A `--check` mode recomputes the expected bytes and exits non-zero listing `missing:` / `out of date:` files.
  Tests: every contract registered (an explicit expected-set literal), write-twice-compare determinism, check-passes-after-write, check-detects-drift.

### 4.6 Testing seams

FakeTransport (the whole LLM testing seam, about 15 lines):

```
class FakeTransport:
    def __init__(self, script: list[TransportResult | Exception]): ...
    def complete(self, **kwargs) -> TransportResult:
        self.requests.append(kwargs)          # record every call's kwargs
        item = self._script.pop(0)            # empty script = test bug, assert
        if isinstance(item, Exception): raise item
        return item
```

A script entry that is an Exception is RAISED (scripts transport failures); a result with `stop_reason="refusal"` scripts a refusal; `payload=None` with `raw_text="RAW_UNPARSEABLE"` scripts malformed output.
`requests` powers every prompt-assembly assertion, the cache-stability pin, and the full-prompt hash pins.
Determinism comes from a frozen clock and a deterministic id generator beside it.
Representative pinned behaviors: retry pacing (`sleeps == [1.0, 2.0]` via an injected sleeper), attempt/sdk_retry sequences in the log rows, the repair-cap exhaustion path, boundary revalidation of schema-enforced output, and timeout pass-through.

The invalid-fixture pattern:

- Layout: `tests/fixtures/{valid,invalid}/<contract>/<name>.json`, each invalid fixture paired with `<name>.expected.json` containing `{"error_substrings": ["...", "..."]}`.
- A tiny loader yields typed fixture objects sorted by path; a MISSING sidecar is a hard `FileNotFoundError`, never a silent skip.
- Every contract test file carries the same two parametrized tests: valid fixtures parse; invalid fixtures raise `ValidationError` whose string contains every expected substring.
  Plus two universal tests per contract: the model is frozen; unknown fields are rejected.
- Discipline: ONE fixture per violation - every field constraint and every model validator has a named fixture that proves it fires (Loop's profile has 14 invalid fixtures mapping 1:1 onto its constraints and validators).
  A valid fixture can encode a policy too (an all-empty proposal is valid: empty over fabrication).

Prompt-version pinning (two layers; an intentional prompt change must bump the version AND replace the pinned hash in the same commit):

1. System-prompt pins: a table of `(constant_name, config, pinned_version, pinned_sha256)`; the test hashes each system-prompt constant and asserts both the version match and the hash match, printing the new hash on failure for copy-paste regeneration.
2. Full-rendered-prompt pins: per node, a builder runs the real adapter against a FakeTransport scripted with TWO responses where the first deliberately fails a deterministic check - so the second call carries a real repair suffix and the repair-formatting bytes are inside the hash.
   Every outbound call's `(system, user_prompt, repair_suffix)` is serialized into a canonical frame text and sha256-pinned.
   Each builder ends with rot-guard asserts that the render still contains its labeled blocks (and still EXCLUDES what must be excluded, e.g. the raw pasted text), so a refactor that silently dropped a block cannot hide behind a stable-but-meaningless hash.
   Exemplars embedded in prompts live as Python dicts validated against the real contracts and serialized with sorted keys at import, keeping prompt bytes stable.

Why this matters: `prompt_version` is a hand-maintained label with no structural link to the bytes; without the pins, an edit without a bump would silently mislabel every call-log row and eval comparison.

### Starmap deltas (kernels)

- Keep the engine nearly whole: transport Protocol, `TransportResult` with cache token classes, retryable/permanent taxonomy with type-name-only messages, contract-capped config, the two nested loops with the exact outcome table, the separate-repair-suffix cache mechanism, full-bytes prompt hash, and the unified violation-line format.
  Only two nodes (prereq extractor, pathway proposer), so two configs; drop `plan_version` from the log (log `run_id` only); keep the debug sink and injected sleeper.
- Keep the call log shape minus plan_version; cost tracking is how you keep the contest budget honest.
- Keep `common/sqlite.py` essentially as specified in 4.3; it is small and exactly right for one-machine SQLite.
  Starmap has three databases: `catalog.db` and `corpus.db` read-only in the image, `sessions.db` (profiles, pathway sets, cache, call log) on the volume.
- Keep the app-assembly order; replace OAuth/session middleware with the `sid` cookie middleware (lazily mint an HttpOnly SameSite=Lax cookie); keep the exception-handler order including the ValidationError-before-ValueError trap, no-cache HTML, GET+HEAD, and the mount-SPA-last rule.
- Keep the contracts conventions wholesale (extra=forbid + frozen, rebuild-through-validate, validator message discipline, one spec doc per contract, generated schemas with `--check`), scaled to Starmap's ~10 contracts.
- Keep FakeTransport, the invalid-fixture pattern (one fixture per validator code for prereq expressions and pathway violations especially), and at least layer-1 prompt-hash pinning; layer-2 is cheap once FakeTransport exists and is worth it for the two prompts.

---

## Appendix: corrections and gotchas recorded during this study

- The corpus manifest is at `backend/corpus/manifest_v1.json` and evalsets at `backend/evalsets/` (not repo root).
- The atlas layout kernel contains NO seeded PRNG; determinism is analytic (golden-angle seeding + fixed anchors + fixed iterations + index-based coincidence nudge + rounding).
  The Lehmer PRNG lives only in the decorative dust-field module.
- Loop's ingest tool has NO sleep-based rate limiting (politeness = per-run cap + timeout + no retries + robots.txt); Starmap's planned 1 req/s bulletin fetcher is new code, not a port.
- Provider-side schema-enforced output must still be boundary-revalidated: a payload can satisfy the wire schema and still violate cross-field contract invariants, and eager SDK validation would escape the repair loop.
- Registry text is stored beside the metadata payload and the content hash is re-checked on READ, not just register, so disk corruption fails loudly.
- Extended thinking must be explicitly disabled on the API call for small `max_tokens` budgets; omitting the parameter can silently enable adaptive thinking that bills inside `max_tokens`.
- Store existence/conflict checks are explicit SELECTs inside the insert transaction, never caught PK violations, so errors stay typed and concurrency-safe.
- Transactions never nest on the shared SQLite connection; read other stores before opening your write transaction.
- Pydantic's `ValidationError` subclasses `ValueError`; register the 422 handler explicitly or it collapses into the 400 path.
- Serve every HTML document `Cache-Control: no-cache` from day one; the SPA-shell-cached-on-a-future-URL incident is real and outlives the fix.
