# Increment 4: Articulation Contracts

Goal: generalize `prereq_expr` into `articulation_expr`, add the seven ASSIST-shaped contracts with specs, fixtures, and generated schemas, rework the reason-code families, and delete the retired Columbia-shaped contracts in the same increment so `make check` stays green throughout.
Binding mechanism references: TR 4.5 (contracts conventions), TR 4.6 (invalid-fixture pattern, schema generation), the spike doc "Agreement payload model", and the captured fixtures in `backend/tests/fixtures/assist/`.
The Columbia-contract deletion was user-approved 2026-07-31.

Discipline per contract (TR 4.5, unchanged): spec doc first, then model, then fixtures, then regenerated schemas, then tests.
Every model uses `FROZEN` from `contracts/base.py`; updates go through `rebuild`; validator messages name the field and quote offending values.

## Part 1: deletions and renames (exact file list, locked)

Delete these files (Columbia-shaped contracts, user-approved 2026-07-31):

- `backend/src/starmap/contracts/course.py`
- `backend/src/starmap/contracts/offering.py`
- `backend/src/starmap/contracts/requirement_group.py`
- `docs/specs/course.schema.md`
- `docs/specs/offering.schema.md`
- `docs/specs/requirement_group.schema.md`
- `backend/schemas/course.schema.json`
- `backend/schemas/offering.schema.json`
- `backend/schemas/requirement_group.schema.json`
- `backend/tests/contracts/test_course.py`
- `backend/tests/contracts/test_offering.py`
- `backend/tests/contracts/test_requirement_group.py`
- the entire directories `backend/tests/fixtures/valid/course/` (3 files), `backend/tests/fixtures/invalid/course/` (32 files), `backend/tests/fixtures/valid/offering/` (2 files), `backend/tests/fixtures/invalid/offering/` (14 files), `backend/tests/fixtures/valid/requirement_group/` (3 files), `backend/tests/fixtures/invalid/requirement_group/` (26 files)

Delete these files because `articulation_expr` supersedes them (the generalization, same approval):

- `backend/src/starmap/contracts/prereq_expr.py`
- `docs/specs/prereq_expr.schema.md`
- `backend/schemas/prereq_expr.schema.json`
- `backend/tests/contracts/test_prereq_expr.py`
- the entire directories `backend/tests/fixtures/valid/prereq_expr/` (5 files) and `backend/tests/fixtures/invalid/prereq_expr/` (16 files)

Nothing else is deleted.
`contracts/corpus_document.py` and its spec, fixtures, schema file, and tests stay exactly as they are (overview doc, "Out of scope").

## Part 2: `contracts/codes.py` rewrite

Replace the module body with the ASSIST-shaped regex, `normalize_course_code`, and `course_code_from_parts` exactly as locked in the overview doc ("Course-code normalization").
Update the module docstring: the regex is now derived from the ASSIST captures (spike doc), not the Columbia bulletin spike.

Rewrite `backend/tests/contracts/test_codes.py`:

- `SPIKE_OBSERVED_SHAPES = ["MATH 1A", "MATH 2AH", "STAT C1000H", "CIS 22C", "CIS 22CH", "CSE 15L", "MATH 20E", "CSE 11"]`, each asserted to normalize to itself and fullmatch the regex.
- Normalization test: `normalize_course_code("  math   1a ") == "MATH 1A"`.
- `course_code_from_parts("STAT", "C1000H") == "STAT C1000H"`.
- Invalid inputs raising `ValueError` matching `"invalid course code"`: `"MATH"` (no number token), `"1A"` (no prefix token), `"MATH 12345"` (5 digits), `"MATH 1ABCD"` (4 trailing letters), `""`.

## Part 3: `contracts/articulation_expr.py` (generalized from `prereq_expr`)

New module `backend/src/starmap/contracts/articulation_expr.py`, spec `docs/specs/articulation_expr.schema.md`.
Start from the deleted `prereq_expr.py` structure; it is a rename plus two deltas.
Everything not listed here carries over unchanged: the structural-discrimination design, `MAX_DEPTH = 3`, `expr_depth`, `_validate_depth`, the depth-error wording, the `RootModel` wrapper, `model_rebuild()` calls.

Locked surface:

- `parse_articulation_expr(data: object) -> object` with the same dispatch logic and error messages as `parse_prereq_expr` (the four discriminating keys are unchanged: `all`, `any`, `course`, `note`).
- `CourseLeaf`: field `course: CourseCode` ONLY.
  Delta 1: `equivalent_ok` is deleted (it encoded a Columbia bulletin idiom; ASSIST equivalence lives in the articulation itself).
- `NoteLeaf`: field `note: str`, 1..2000 chars, control-character hygiene via `reject_control_chars`.
  Delta 2: the cap widens from 500 to 2000 because ASSIST advisement prose length is unverified (fixture-pending, overview doc); record this rationale in the spec.
- `AllOf` / `AnyOf`: unchanged shapes over `ArticulationExprField`.
- `ArticulationExpr = AllOf | AnyOf | CourseLeaf | NoteLeaf`; `ArticulationExprField = Annotated[ArticulationExpr, BeforeValidator(parse_articulation_expr)]`; `ArticulationExprRoot(RootModel[ArticulationExprField])`.

Spec example and the `plan_example.json` valid fixture: the plan's sending-side example verbatim (`docs/STARMAP_PATHFINDERS_PLAN.md`, "Example sending-side expression"), i.e. the MATH 1A/1B honors `any`-of-`all` tree with its note leaf.
The spec keeps the round-trip clause: `model_dump(mode="json", exclude_defaults=True)` of the parsed example equals the example object.

Fixtures (new directories `valid/articulation_expr/`, `invalid/articulation_expr/`):

- Valid: `plan_example.json`, `single_course_leaf.json` (`{"course": "MATH 1A"}`), `unnormalized_course_leaf.json` (`{"course": "  math  1a "}`), `depth_three.json`, `note_leaf.json`.
- Invalid (each with its `.expected.json` sidecar): `bad_course_code.json`, `depth_four.json`, `empty_all_group.json`, `empty_any_group.json`, `note_control_char.json`, `note_empty.json`, `note_too_long.json` (2001 chars), `unknown_keys.json`.

Test file `backend/tests/contracts/test_articulation_expr.py`: port every test from the deleted `test_prereq_expr.py`, renamed, with ASSIST-shaped codes; keep the four standard tests, the plan-example round trip, the dispatch tests, and the depth tests.

## Part 4: reason-code rework (`contracts/reason_codes.py`)

Delete `PrereqExtractionCode`, `BuildCode`, and `CorpusCode` per the overview doc's one-time pivot exception; keep `LlmReasonCode` unchanged.
Add, exactly:

```python
class EvaluationFindingCode(StrEnum):
    TRANSFERS_CLEAN = "transfers_clean"
    ADVISEMENT_NOTE = "advisement_note"
    PARTIAL_SERIES = "partial_series"
    FUZZY_MATCH = "fuzzy_match"
    STALE_YEAR = "stale_year"
    NO_ARTICULATION = "no_articulation"
    STILL_OWED = "still_owed"
    DOUBLE_COUNT_RISK = "double_count_risk"
    UNRESOLVED = "unresolved"

class TriageBucket(StrEnum):
    TRANSFERS_CLEAN = "transfers_clean"
    AT_RISK = "at_risk"
    NO_ARTICULATION = "no_articulation"
    STILL_OWED = "still_owed"

BUCKET_FOR_CODE: dict[EvaluationFindingCode, TriageBucket] = {
    EvaluationFindingCode.TRANSFERS_CLEAN: TriageBucket.TRANSFERS_CLEAN,
    EvaluationFindingCode.ADVISEMENT_NOTE: TriageBucket.AT_RISK,
    EvaluationFindingCode.PARTIAL_SERIES: TriageBucket.AT_RISK,
    EvaluationFindingCode.FUZZY_MATCH: TriageBucket.AT_RISK,
    EvaluationFindingCode.STALE_YEAR: TriageBucket.AT_RISK,
    EvaluationFindingCode.DOUBLE_COUNT_RISK: TriageBucket.AT_RISK,
    EvaluationFindingCode.UNRESOLVED: TriageBucket.AT_RISK,
    EvaluationFindingCode.NO_ARTICULATION: TriageBucket.NO_ARTICULATION,
    EvaluationFindingCode.STILL_OWED: TriageBucket.STILL_OWED,
}

class AssistBuildCode(StrEnum):
    SESSION_BOOTSTRAP_FAILED = "session_bootstrap_failed"
    AGREEMENT_FETCH_FAILED = "agreement_fetch_failed"
    ENVELOPE_INVALID = "envelope_invalid"
    FIELD_DECODE_FAILED = "field_decode_failed"
    ARTICULATION_TYPE_UNSUPPORTED = "articulation_type_unsupported"
    COURSE_CODE_UNPARSEABLE = "course_code_unparseable"
    MIXED_GROUP_CONJUNCTION = "mixed_group_conjunction"
    ADVISEMENT_SHAPE_UNKNOWN = "advisement_shape_unknown"
    TEMPLATE_SHAPE_UNSUPPORTED = "template_shape_unsupported"
    INSTITUTION_KIND_UNKNOWN = "institution_kind_unknown"
    COURSE_PROJECTION_CONFLICT = "course_projection_conflict"

class RetrievalCode(StrEnum):
    FTS5_UNAVAILABLE = "fts5_unavailable"
    INSTITUTION_NOT_INDEXED = "institution_not_indexed"
```

`unresolved` maps to `at_risk`, not `no_articulation`, locked with this rationale for the spec: red claims a fact about the agreement ("no articulation exists"); an unresolved course is an input-quality problem the student can fix, which is amber's "needs attention" semantics.

Update `docs/specs/reason_codes.schema.md`: one meaning line per member (producers named per docs 02-04), the `BUCKET_FOR_CODE` table as a normative table tests assert against, and the recorded pivot exception paragraph.
Update `backend/tests/contracts/test_reason_codes.py`: exact member sets per family, `BUCKET_FOR_CODE` totality (every `EvaluationFindingCode` has a bucket), and snake_case value checks, in the existing file's style.

## Part 5: the seven new contracts

All field names below are locked; all are derived from the captured fixtures (overview doc table).
Shared conventions: institution ids are ASSIST integer ids (`int`, `gt=0`); every free-text field gets `reject_control_chars`; year labels match `^[0-9]{4}-[0-9]{4}$` with an after-validator asserting the second year equals the first plus one.

### `contracts/institution.py` (spec: `docs/specs/institution.schema.md`)

| Field | Type | Constraints |
|---|---|---|
| `assist_id` | int | `gt=0`; the ASSIST institution id is the sole id (locked deviation from the plan's two-column `institutions(id, assist_id, ...)` sketch; a second internal id would be unused generality). |
| `code` | str | 1..8 chars, pattern `^[A-Z][A-Z0-9]{0,7}$`; the fixture pads with trailing spaces, so normalization (strip) happens in `assist/normalize.py`, not here. |
| `name` | str | 1..200, control-char hygiene. |
| `kind` | `Literal["cc", "uc", "csu"]` | Derivation from `isCommunityCollege`/`category` is normalize-side (doc 02); category 5 (private) institutions never reach this contract. |

No model validators beyond the field constraints.
Invalid fixtures: `assist_id_zero`, `bad_code_pattern`, `name_empty`, `bad_kind`.
Valid fixtures transcribed from `institutions.json`: `de_anza.json` (113, `DAC`, cc), `ucsd.json` (7, `UCSD`, uc), `sjsu.json` (39, `SJSU`, csu).

### `contracts/agreement.py` (spec: `docs/specs/agreement.schema.md`)

`Agreement`:

| Field | Type | Constraints |
|---|---|---|
| `agreement_id` | str | pattern `^agr_[0-9a-f]{16}$`. |
| `assist_key` | str | pattern `^[0-9]+/[0-9]+/to/[0-9]+/(Major\|Department)/.+$` (both observed key formats: Major carries a GUID tail, Department an integer tail). |
| `category` | `Literal["major", "dept"]` | Closed for v1 (overview doc). |
| `sending_institution_id` | int | `gt=0`. |
| `receiving_institution_id` | int | `gt=0`. |
| `academic_year_id` | int | `gt=0`. |
| `academic_year_label` | str | year-label pattern + consecutive-years validator. |
| `label` | str | 1..300, hygiene; the report label from the agreements list endpoint. |
| `publish_date` | str | 1..40; VERBATIM provenance string (ASSIST emits 7-digit fractional seconds, e.g. `2026-06-08T23:04:32.5510019`; parsing it buys nothing and risks precision churn; never computed on). |

Model validators:

- `agreement_id == "agr_" + sha256_hex(assist_key)[:16]` (derived-id house pattern, `sha256_hex` from `common/ids.py`; error quotes both values).
- `sending_institution_id != receiving_institution_id`.
- key/category coherence: the key's fourth segment is `Major` iff `category == "major"`, `Department` iff `"dept"`.
- key/id coherence: the key's first three integers equal `academic_year_id`, `sending_institution_id`, `receiving_institution_id` in that order (key format per the spike doc).

Also in this module, the still-owed template models (major agreements only; shapes from `templateAssets` in the major fixture):

- `TemplateCell`: `cell_id: str` (pattern `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`), `course: ReceivingCourse` (imported from `contracts/articulation.py`).
  The `cell_id` is the join key to `Articulation.template_cell_id`; a cell with no matching articulation means "no articulation published" (overview doc payload facts).
- `TemplateSection`: `position: int` (`ge=0`), `cells: list[TemplateCell]` (min length 1).
- `RequirementGroupAsset`: `group_id: str` (same GUID pattern), `position: int` (`ge=0`), `conjunction: Literal["And", "Or"]`, `sections: list[TemplateSection]` (min length 1), `advisements: list[str]` (default empty; each 1..2000, hygiene).
  Normalize-side mapping (null instruction means `And`, `Conjunction` instruction supplies the value, rows flatten to cells) is locked in doc 02; the contract only holds the normalized result.

Invalid fixtures: `bad_id_derivation`, `bad_key_pattern`, `category_key_mismatch`, `same_institutions`, `key_ids_mismatch`, `bad_year_label`, `nonconsecutive_year_label`, `template_cell_bad_guid`, `requirement_group_empty_sections`.
Valid fixtures transcribed from the captures: `major_cse_cs.json` (from the major fixture's envelope plus its report entry) and `dept_math.json`.

### `contracts/articulation.py` (spec: `docs/specs/articulation.schema.md`)

`ReceivingCourse` (from the receiving `course` objects in both agreement fixtures):

| Field | Type | Constraints |
|---|---|---|
| `course_code` | CourseCode | normalized. |
| `prefix` | str | 1..16, pattern `^[A-Z][A-Z0-9&/. \-]{0,15}$`. |
| `number` | str | 1..8, pattern `^[A-Z0-9.\-]{1,8}$`. |
| `title` | str | 1..300, hygiene. |
| `units_min` | float | `gt=0`, `le=20`. |
| `units_max` | float | `le=20`; validator `units_max >= units_min`. |

Model validator: `course_code == course_code_from_parts(prefix, number)` (error quotes all three).

`Articulation`:

| Field | Type | Constraints |
|---|---|---|
| `agreement_id` | str | pattern `^agr_[0-9a-f]{16}$`. |
| `position` | int | `ge=0`; the index in the decoded `articulations` array, the citation position (findings axiom). |
| `template_cell_id` | str \| None | GUID pattern when present; None for dept agreements. |
| `receiving_course` | ReceivingCourse | required. |
| `sending_expr` | ArticulationExprField \| None | None means "No Course Articulated" (null `sendingArticulation` or empty `items`, overview doc). |
| `no_articulation_reason` | str \| None | 1..500, hygiene; observed null in captures but the field exists in the payload. |
| `advisements` | list[str] | default empty; each 1..2000, hygiene; articulation-level and sending-articulation-level advisement texts (group/course-level texts become note leaves inside `sending_expr`, doc 02). |

Model validator: `no_articulation_reason` non-null requires `sending_expr` null (a reason for having no articulation cannot coexist with an expression).

Invalid fixtures: `reason_with_expr`, `bad_agreement_id`, `negative_position`, `receiving_units_max_below_min`, `receiving_code_parts_mismatch`, `advisement_control_char`, `bad_template_cell_guid`.
Valid fixtures transcribed from the captures (names carry provenance): `math20d_honors_or_regular.json` (MATH 20D, two single-course groups joined `Or`), `math20e_and_series.json` (MATH 20E, one `And` group MATH 1C + MATH 1D), `math10b_no_articulation.json` (dept MATH 10B, `sending_expr` null), `synthetic_advisement.json` (a hand-built articulation with a note leaf and an `advisements` entry, exercising the fixture-pending mechanism with synthetic text clearly labeled as such in the fixture).

### `contracts/cc_course.py` (spec: `docs/specs/cc_course.schema.md`)

`CcCourse`, the sending-side projection row (autocomplete vocabulary, transcript-resolution vocabulary, FTS index rows: one projection, three consumers):

| Field | Type | Constraints |
|---|---|---|
| `institution_id` | int | `gt=0`. |
| `course_code` | CourseCode | normalized. |
| `prefix` | str | same pattern as `ReceivingCourse.prefix`. |
| `number` | str | same pattern as `ReceivingCourse.number`. |
| `title` | str | 1..300, hygiene. |
| `units_min` | float | `gt=0`, `le=20`. |
| `units_max` | float | `le=20`; validator `units_max >= units_min`. |

Model validator: `course_code == course_code_from_parts(prefix, number)`.
Invalid fixtures: `institution_id_zero`, `code_parts_mismatch`, `units_max_below_min`, `units_min_zero`, `title_empty`.
Valid fixtures from the captures: `math_1a.json`, `stat_c1000h.json`, `cis_22c.json`.

### `contracts/target_course.py` (spec: `docs/specs/target_course.schema.md`)

`TargetCourse`: field-for-field identical to `CcCourse` (locked: duplication over inheritance, matching the house no-hierarchy style; docstrings cross-reference).
The plan's sketch shows a single `units` column; locked deviation: keep `units_min`/`units_max` because the payload carries both (`minUnits`/`maxUnits`) and variable-unit receiving courses exist in the wild.
Invalid fixtures: `code_parts_mismatch`, `units_max_below_min`.
Valid fixtures: `math_20d.json`, `cse_11.json`.

### `contracts/evaluation.py` (spec: `docs/specs/evaluation.schema.md`)

This module is the findings object: the wire shape of `POST /api/evaluations` responses in Week 2 AND the petition prompt vocabulary (the second vocabulary gate); its determinism and citation completeness are axioms.

`StudentCourse` (the resolved input the evaluator consumes):

| Field | Type | Constraints |
|---|---|---|
| `course_code` | CourseCode | normalized. |
| `title` | str \| None | 1..300, hygiene. |
| `units` | float | `gt=0`, `le=20`. |
| `resolution` | `Literal["exact", "fuzzy_match"]` | how the input resolved against the `cc_courses` projection; unresolved input never becomes a `StudentCourse`. |

`Citation` (the ground-truth pointer every finding carries):

| Field | Type | Constraints |
|---|---|---|
| `assist_key` | str | the agreement key pattern from `Agreement.assist_key`. |
| `position` | int | `ge=0`; the articulation position. |
| `year_label` | str | year-label pattern + consecutive-years validator. |

`Finding`:

| Field | Type | Constraints |
|---|---|---|
| `code` | EvaluationFindingCode | |
| `bucket` | TriageBucket | validator: `bucket == BUCKET_FOR_CODE[code]` (single source of bucket truth). |
| `student_course_codes` | list[CourseCode] | unique via `find_duplicates`; may be empty (still_owed findings). |
| `receiving_course_code` | str \| None | CourseCode-normalized when present. |
| `receiving_course_title` | str \| None | 1..300, hygiene. |
| `units` | float | `ge=0`; units attributed to this finding (semantics locked in doc 03). |
| `citation` | Citation \| None | validator below. |
| `advisements` | list[str] | default empty; each 1..2000, hygiene. |
| `detail` | str \| None | 1..500, hygiene; deterministic template text, never LLM output. |

Citation validator, locked: codes `{transfers_clean, advisement_note, partial_series, fuzzy_match, stale_year, double_count_risk, still_owed}` REQUIRE a citation; codes `{no_articulation, unresolved}` require citation None (there is no articulation to cite; the pair context lives on the envelope).
Second validator: `code == advisement_note` requires non-empty `advisements`.

`UnitsSummary`:

| Field | Type | Constraints |
|---|---|---|
| `clean_units`, `at_risk_units`, `no_articulation_units`, `still_owed_units` | float | each `ge=0`. |
| `at_risk_dollars`, `no_articulation_dollars` | float \| None | `ge=0` when present; None when the cost table lacks the target institution (doc 03). |

`Evaluation`:

| Field | Type | Constraints |
|---|---|---|
| `evaluation_id` | str | pattern `^eval_[0-9a-f]{16}$` (minted via `IdGenerator.new_id("eval")`, not derived). |
| `sending_institution_id` | int | `gt=0`. |
| `receiving_institution_id` | int | `gt=0`; validator: differs from sending. |
| `major_key` | str | agreement-key pattern; the major agreement evaluated. |
| `dept_keys` | list[str] | default empty; unique; each the agreement-key pattern. |
| `year_id` | int | `gt=0`. |
| `year_label` | str | year-label pattern + consecutive validator. |
| `student_courses` | list[StudentCourse] | min length 1; `course_code` values unique. |
| `findings` | list[Finding] | may be empty; ORDER is produced deterministically by the evaluator (sort key locked in doc 03) but deliberately not contract-enforced (the contract cannot know the sort without duplicating evaluator logic). |
| `units` | UnitsSummary | required. |
| `created_at` | datetime | timezone-aware (validator per the TR 3.5 pattern catalog). |

Invalid fixtures: `bucket_code_mismatch`, `advisement_note_without_advisements`, `citation_missing_for_clean`, `citation_present_for_unresolved`, `same_institutions`, `duplicate_student_courses`, `naive_created_at`, `bad_evaluation_id`, `negative_units_summary`, `student_units_zero`.
Valid fixtures: `minimal.json` (one clean finding) and `demo_shape.json` (one finding of every code with correct buckets and citations, the reference shape for doc 03 and the Week 2 petition validator).

## Part 6: schema registry and cross-cutting test updates

- `backend/scripts/generate_schemas.py` `CONTRACTS` registry, exact final value: `{"agreement": Agreement, "articulation": Articulation, "articulation_expr": ArticulationExprRoot, "cc_course": CcCourse, "corpus_document": CorpusDocument, "evaluation": Evaluation, "institution": Institution, "target_course": TargetCourse}`.
  Note: `RequirementGroupAsset` and the other nested models are reachable through their parents' schemas and are not registered separately.
- Regenerate `backend/schemas/`; the committed set becomes exactly those eight `.schema.json` files.
- `backend/tests/test_generate_schemas.py`: update `EXPECTED_CONTRACTS` to the eight names; the drift test mutates `institution.schema.json` instead of the deleted `course.schema.json`.
- New test `backend/tests/contracts/test_assist_fixture_alignment.py`, the increment's exit proof that contracts fit the captures without duplicating normalizer logic: load `agreement_major_cse_cs_113_to_7_y76.json` and `agreement_dept_math_113_to_7_y76.json`, decode the double-encoded `articulations` field (`json.loads` twice), and assert the fixture facts the contracts were designed from: 8 and 11 articulation entries, every inner articulation `type` is `Course`, MATH 10B/10C carry null `sendingArticulation`, MATH 20D has two groups joined by one `Or` conjunction, every observed `{prefix} {courseNumber}` pair passes `normalize_course_code`, and every `attributes` list at all four levels is empty (the advisement fixture-pending precondition; this assertion is REMOVED when S9c lands the advisement fixture).

## Exit criteria

- `make check` green with the deletions and additions in the same commit; no orphaned imports (grep for `prereq_expr`, `from starmap.contracts.course`, `offering`, `requirement_group` returns nothing under `backend/src` and `backend/tests`).
- Eight spec docs current in `docs/specs/` (seven new plus the updated `reason_codes.schema.md`); the deleted four spec docs are gone.
- Every field constraint and model validator above has a named invalid fixture that fires; valid fixtures transcribed from the ASSIST captures parse.
- `test_assist_fixture_alignment.py` green against the untouched captured fixtures.
