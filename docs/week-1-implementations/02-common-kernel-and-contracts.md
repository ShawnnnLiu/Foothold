# Increment 2: Common Kernel and First Contracts

Goal: the shared kernel every region imports, the contract conventions machinery, and the first six contracts with specs, fixtures, and generated schemas.
Binding mechanism references: TR 4.3 (SQLite kernel), TR 4.5 (contracts conventions), TR 4.6 (fixture pattern, schema generation).

## Part 1: `common/` kernel

### `common/errors.py`

One base class: `StarmapError(Exception)` with `__init__(self, message: str, *, reason_code: str | None = None)` storing both.
Every typed error in the repo derives from it; no raw exception crosses a region boundary.
Region-specific error classes live in their regions and subclass this.

### `common/sqlite.py`

Implement TR 4.3 exactly; the section is the spec.
Surface: `SqliteDatabase(path: Path | str)` with `transaction()` and `read()` context managers, and `ensure_schema(db, component: str, *, version: int, statements: Sequence[str])`.
Locked behaviors, restated as the test list: autocommit connection with explicit `BEGIN IMMEDIATE`; WAL; foreign keys on; one `RLock` serializing transactions and reads; commit on clean exit, rollback on any exception; transactions never nest (document the read-before-write rule in the module docstring); `SchemaVersionMismatchError(StarmapError)` carrying component, on-disk, and expected versions; idempotent re-`ensure_schema` at the same version.

### `common/clock.py`

`Clock` Protocol: `now() -> datetime` (timezone-aware UTC) and `monotonic() -> float`.
`SystemClock` implements both via `datetime.now(timezone.utc)` and `time.monotonic`.
Test twin `FrozenClock(start: datetime)` lives in `backend/tests/support/clocks.py`, with `advance(seconds)`.

### `common/ids.py`

`IdGenerator` Protocol: `new_id(prefix: str) -> str` returning `f"{prefix}_{uuid4().hex[:16]}"`.
`UuidIdGenerator` for production; `SequentialIdGenerator` test twin (`prefix_0000000000000001`, ...) in `tests/support/ids.py`.
Content-derived ids (doc/snapshot/chunk/requirement-group) are NOT here; they live beside their owning regions with their derivation formulas.
Also here: `sha256_hex(text: str) -> str`, the single hash helper the whole repo uses.

### `common/dbdump.py`

`canonical_dump(path: Path) -> str`, the single definition of SQLite artifact identity (README, "Committed-artifact identity").
Algorithm: open read-only; list tables from `sqlite_master` where `type='table'`, excluding only `sqlite_` internals; `schema_version` is deliberately included so component-version drift fails the check.
For each table in sorted name order: emit the `CREATE TABLE` SQL from `sqlite_master` with whitespace runs collapsed to single spaces, then every row as `json.dumps(list_of_values, sort_keys=True)` ordered by all columns ascending (`SELECT * FROM t ORDER BY 1, 2, ... n`), then a blank line.
Virtual-table shadow tables (FTS5 internals, names containing `_fts`) are excluded from row dumps but their declared virtual `CREATE VIRTUAL TABLE` statements are included.
Purpose: `--check` in build tooling compares `canonical_dump(committed)` to `canonical_dump(regenerated)`.

## Part 2: contracts machinery

### `contracts/base.py`

`FROZEN = ConfigDict(extra="forbid", frozen=True)` used by every model.
`rebuild(model: T, **updates) -> T` implementing `type(model).model_validate(model.model_dump() | updates)`; the only sanctioned update path.

### `contracts/dedup.py`

`casefold_key(s: str) -> str` (casefold + whitespace-collapse) and `find_duplicates(items: Iterable[str]) -> list[str]` returning first-seen spellings of case-insensitive duplicates.
Used by contracts and kernels both, so joins and uniqueness agree everywhere (TR 4.5).

### `contracts/codes.py`

`COURSE_CODE_RE`: the regex finalized by the increment 1 spike (default `^[A-Z]{2,4} [A-Z]{1,2}[0-9]{4}$`; if the spike widened it, use the spike's recorded final form and note it in the spec).
`normalize_course_code(raw: str) -> str`: uppercase, collapse internal whitespace to one space, strip; raises `ValueError` naming the input if the result fails `COURSE_CODE_RE`.

## Part 3: the six contracts

Discipline per contract (TR 4.5): write `docs/specs/<name>.schema.md` FIRST, then the model, then fixtures, then regenerate schemas, then tests.
Spec docs carry the field table, constraint list, validator inventory, and one example; tests may assert against their normative tables.

### `contracts/reason_codes.py` (spec: `docs/specs/reason_codes.schema.md`)

`StrEnum` families, snake_case values, append-only forever:

- `LlmReasonCode`: `auth_failed`, `rate_limited`, `call_failed`, `retry_limit_exceeded`, `refusal`, `truncated`, `malformed_output`, `schema_rejected`, `repair_limit_exceeded`.
- `PrereqExtractionCode`: `unknown_course_leaf`, `unaccounted_linked_code`, `expr_too_deep`.
- `BuildCode`: `dept_fetch_failed`, `dept_parse_failed`, `dept_excluded`.
- `CorpusCode`: `content_hash_mismatch`, `document_conflict`, `unknown_document`, `empty_snapshot`, `fts5_unavailable`, `snapshot_not_indexed`.

Week 2 adds the pathway violation family to this module.
The spec doc lists every member with a one-line meaning; adding a member updates the spec in the same commit.

### `contracts/prereq_expr.py` (spec: `docs/specs/prereq_expr.schema.md`)

Recursive discriminated union `PrereqExpr = AllOf | AnyOf | CourseLeaf | NoteLeaf`:

- `CourseLeaf`: `course` (normalized via `normalize_course_code` validator against `COURSE_CODE_RE`), `equivalent_ok: bool = False`.
- `NoteLeaf`: `note`, 1..500 chars, control-character hygiene (reject codepoints < 0x20 except `\n\r\t`, reported as `U+XXXX`).
- `AllOf`: `all: list[PrereqExpr]`, min length 1.
- `AnyOf`: `any: list[PrereqExpr]`, min length 1.

Model validator on the group types: nesting depth <= 3, where a bare leaf is depth 1 and each group level adds 1; the error message quotes the offending depth.
Serialization must round-trip the plan's example verbatim (`docs/STARMAP_PATHFINDERS_PLAN.md` example block); make that a valid fixture.
Discriminator note: these are structurally discriminated (distinct required keys), so use a pydantic `Union` with `model_validator` dispatch or tagged parsing helper `parse_prereq_expr(data: dict) -> PrereqExpr`; lock: implement `parse_prereq_expr` in the same module and have `Course.prereq_expr` typed as the union with a `BeforeValidator` calling it.

### `contracts/course.py` (spec: `docs/specs/course.schema.md`)

Fields: `course_code` (normalized, pattern), `title` (1..300, control-char hygiene), `points_min: float` (> 0, <= 20), `points_max: float` (>= points_min, <= 20), `description: str | None` (1..8000 when present), `prereq_prose: str | None` (1..4000), `prereq_expr: PrereqExpr | None`, `prereq_confidence: Literal["parsed", "fallback_flat", "none"]`, `bulletin_url` (http/https, non-empty), `department_code: str` (1..8, uppercase).
Cross-field validator: `prereq_confidence == "none"` iff `prereq_expr is None`; `parsed`/`fallback_flat` require a non-null expr; messages name both fields.
Deviation from the plan's single `points` column, recorded here as the decision: variable-point courses (research, independent study) are real, so the contract and the `courses` table carry `points_min`/`points_max`; fixed-point courses store the same value twice.

### `contracts/offering.py` (spec: `docs/specs/offering.schema.md`)

Fields: `course_code` (pattern), `term: Literal["fall", "spring", "summer"]`, `year: int` (2020..2035), `instructors: list[str]` (each 1..100 chars, case-insensitively unique via `find_duplicates`, may be empty).

### `contracts/requirement_group.py` (spec: `docs/specs/requirement_group.schema.md`)

Fields: `requirement_group_id` (pattern `^rg_[0-9a-f]{16}$`), `major_id: str` (1..64, lowercase slug pattern `^[a-z0-9-]+$`), `name` (1..200), `rule_kind: Literal["all", "choose_n", "note"]`, `member_courses: list[str]` (codes, unique, may be empty only for `note`), `choose_n: int | None`, `note_text: str | None` (1..1000).
Derivation, owned by the model validator: `requirement_group_id == "rg_" + sha256_hex(f"{major_id}\n{name}")[:16]`.
Kind-conditional validator: `choose_n` requires `choose_n` in 1..len(member_courses) and forbids `note_text`; `all` forbids both `choose_n` and `note_text` and requires non-empty members; `note` requires `note_text` and forbids `choose_n`.

### `contracts/corpus_document.py` (spec: `docs/specs/corpus_document.schema.md`)

Per TR 1.1 with the Starmap deltas: drop `track_tags` entirely.
Fields: `doc_id` (`^doc_[0-9a-f]{16}$`), `source_url` (non-empty), `source_type: Literal["bulletin_course", "bulletin_requirement"]`, `license_note` (non-empty), `date_collected: date`, `source_published_date: date | None`, `content_hash` (`^[0-9a-f]{64}$`), `title` (non-empty).
Model validators: `doc_id` equals `derive_doc_id(source_url, date_collected)` (formula per TR 1.1, implemented in `retrieval/`, re-implemented inline in the validator via `sha256_hex`); `source_published_date <= date_collected`.
Document text is not a field (TR 1.1 rationale).

## Part 4: fixture harness

Layout: `backend/tests/fixtures/{valid,invalid}/<contract>/<name>.json`; every invalid fixture has `<name>.expected.json` containing `{"error_substrings": [...]}`.
Loader in `backend/tests/support/fixtures.py`: yields `(contract_name, path, payload, expected_substrings | None)` sorted by path; a missing sidecar raises `FileNotFoundError`.
Each contract test file carries the four standard tests (TR 4.6): valid fixtures parse; invalid fixtures raise `ValidationError` containing every expected substring; model is frozen (mutation raises); unknown field rejected.
Discipline: one invalid fixture per field constraint and per model validator branch.
Minimum inventory this increment: prereq_expr (empty group, note too long, control char, depth 4, bad course code), course (each bound, the confidence/expr cross-field both directions, points_max < points_min), offering (bad term, year bounds, duplicate instructor case-insensitively), requirement_group (each kind-conditional branch, bad derived id), corpus_document (bad id derivation, hash pattern, published-after-collected).

## Part 5: generated schemas

`backend/scripts/generate_schemas.py` replacing the increment 0 stub.
`CONTRACTS: dict[str, type[BaseModel]]` registry literal: `course`, `prereq_expr` (the union's wrapper: register `AllOf`, `AnyOf`, `CourseLeaf`, `NoteLeaf` under one `prereq_expr` schema via a `RootModel`), `offering`, `requirement_group`, `corpus_document`.
Output `backend/schemas/<name>.schema.json`, bytes exactly `json.dumps(model.model_json_schema(mode="serialization"), indent=2, sort_keys=True) + "\n"` (TR 4.5).
`--check` recomputes and exits non-zero listing `missing:` / `out of date:` files; default mode writes.
Tests: every registered contract has a committed file; write-twice determinism; check-detects-drift (tmp copy, mutate, assert failure).

## Exit criteria

- `make check` green including the now-real `schema-check`.
- All six spec docs exist in `docs/specs/`; every constraint has a named invalid fixture that fires.
- Kernel test list from Part 1 green, including reopen-persistence and schema-version-mismatch.
- `canonical_dump` has a unit test: build two dbs with identical logical content in different insert orders, assert equal dumps; mutate one row, assert dumps differ.
