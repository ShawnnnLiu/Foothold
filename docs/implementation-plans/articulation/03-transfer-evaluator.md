# Increment 6: The Deterministic Transfer Evaluator

Goal: pure functions from (resolved student courses, stored agreements) to a typed `Evaluation`, plus the triage board view-model with units and dollar totals.
Binding references: the plan's "The transfer evaluation algorithm" section (the buckets and sub-reasons are its list, verbatim), the `evaluation` contract locked in doc 01, and the testing strategy's fixture-per-reason-code rule.
No LLM, no network, no wall clock inside the evaluator (the `Evaluation.created_at` stamp is injected by the caller via `Clock`).

## Package moves

Create `backend/src/starmap/transfer/` with modules `__init__.py`, `evaluate.py`, `triage.py`, `costs.py`.
Delete the empty pre-pivot `backend/src/starmap/prereqs/` package (plan architecture section).
`transfer/` imports only `common/` and `contracts/` (region-boundary axiom); it reads the db through `assist/store.py` ONLY at the composition root (`scripts/evaluate_student.py`), never inside the pure functions.

## `transfer/evaluate.py`

### Expression evaluation

`ExprOutcome` frozen: `state: Literal["satisfied", "partial", "unsatisfied"]`, `matched: tuple[str, ...]` (student codes used, sorted), `missing: tuple[str, ...]` (codes that would complete the path, sorted), `notes: tuple[str, ...]` (note texts encountered on the evaluated path, in tree order).

`evaluate_expr(expr: ArticulationExpr, courses: frozenset[str]) -> ExprOutcome`, locked semantics:

- `CourseLeaf`: `satisfied` with `matched={course}` when the code is in the set; else `unsatisfied` with `missing={course}`.
- `NoteLeaf`: `unsatisfied`, empty matched/missing, `notes=(note,)`; a note NEVER satisfies anything (axiom) and never counts toward a group's course arithmetic.
- `AllOf`: evaluate all children; course-bearing children are those whose subtree contains at least one `CourseLeaf`.
  State: `satisfied` when there is at least one course-bearing child and every course-bearing child is `satisfied`; `partial` when at least one course-bearing child is `satisfied` or `partial` but not all are `satisfied`; else `unsatisfied` (including the all-notes group, the "note-only articulation" edge).
  `matched`/`missing` are unions over course-bearing children; `notes` is the union over ALL children (every branch of an `all` is required context).
- `AnyOf`: pick the best child by state (`satisfied` > `partial` > `unsatisfied`), tie broken by earliest list index (deterministic); the outcome is the chosen child's outcome (its state, matched, missing, and notes only; unchosen branches contribute nothing).

### Classification

`evaluate_pair(student_courses: list[StudentCourse], bundle: AgreementBundle) -> list[Finding]` where `AgreementBundle` is a frozen container built by the composition root: the major `Agreement` with its `Articulation` and `RequirementGroupAsset` lists, dept agreements (each with articulations) sorted by `assist_key`, and `latest_year_id: int` (the `MAX(academic_year_id)` for the pair, per doc 02).

Locked algorithm, in order:

1. Course set = the student `course_code` values (already normalized and unique per the contract).
2. Evaluate every articulation with a non-null `sending_expr` across ALL agreements in the bundle, major first, then dept agreements in sorted order, articulations by `position`.
3. Per articulation outcome, emit at most one finding:
   - `satisfied` with empty path notes and empty `Articulation.advisements`, all matched inputs resolved `exact`, and the agreement's year equal to `latest_year_id` -> `transfers_clean`.
   - `satisfied` otherwise -> ONE at-risk finding with the highest-priority applicable code, priority locked as `advisement_note` (path notes or articulation advisements non-empty) > `fuzzy_match` (any matched input resolved `fuzzy_match`) > `stale_year` (agreement year below `latest_year_id`); lower-priority factors are still surfaced: notes and advisements go in `advisements`, everything else in `detail`.
   - `partial` -> `partial_series`, with `detail` naming matched and missing codes (e.g. `matched MATH 1C; missing MATH 1D`).
   - `unsatisfied` -> no finding (the receiving side may still surface via still-owed).
   Finding fields: `student_course_codes` = the outcome's matched codes; `receiving_course_code`/`receiving_course_title` from the articulation's receiving course; `units` = sum of the matched student courses' units; `citation` = `(agreement.assist_key, articulation.position, agreement.academic_year_label)`.
4. Coverage: a student course used (`matched`) by at least one `satisfied` or `partial` articulation is covered; each uncovered course -> one `no_articulation` finding (`student_course_codes=[code]`, `units` = that course's units, no citation per the contract).
5. Double-use: a student course matched by two or more `satisfied` articulations where at least one of those articulations has non-empty notes or advisements -> one `double_count_risk` finding per such course, citing the FIRST involved articulation in evaluation order, `detail` listing every involved `assist_key:position`.
6. `unresolved` (defense-in-depth; the primary producer is the Week 2 transcript gate): the composition root re-checks every requested course against the `cc_courses` projection before building `StudentCourse` rows; a code not in the projection becomes an `unresolved` finding (`units` from the request when supplied, else 0) and is excluded from the course set.
   The evaluator itself never sees unresolved input.
7. Still-owed, major agreement only (dept agreements have no template): for each `RequirementGroupAsset`, a cell is satisfied when an articulation with `template_cell_id == cell.cell_id` exists and its expression evaluated `satisfied` (notes do not block cell satisfaction; the at-risk finding already carries them); a cell with no matching articulation is unsatisfied (overview doc payload facts).
   A section is satisfied when every cell is satisfied.
   The group is satisfied under `conjunction == "And"` when every section is satisfied, under `"Or"` when at least one section is.
   Each unsatisfied group -> ONE `still_owed` finding: `receiving_course_code`/`title` set when exactly one cell is owed, else None with `detail` enumerating owed cells joined by the group conjunction (e.g. `CSE 15L or CSE 29`); `units` = for `And`, the sum of owed cells' `units_min`; for `Or`, the minimum over sections of that section's owed-cell `units_min` sum (the cheapest completion, deterministic); `citation` = the agreement's key with `position` of the FIRST owed cell's articulation when one exists, else position 0 (the contract requires a citation for `still_owed`; the agreement key and year are the load-bearing parts).
8. Ordering, locked: findings sort by `(bucket rank, code value, receiving_course_code or "", first student_course_code or "")` with bucket rank `transfers_clean=0, at_risk=1, no_articulation=2, still_owed=3`; the view-model preserves this order.

`build_evaluation(...)` assembles the `Evaluation` contract object: findings from `evaluate_pair`, `UnitsSummary` below, `evaluation_id` from the injected `IdGenerator`, `created_at` from the injected `Clock`.

### Units accounting (into `UnitsSummary`)

- `clean_units` = sum of units of student courses whose BEST finding is `transfers_clean`; a student course's best finding is the first covering finding in bucket-rank order (clean beats at-risk beats none), so a course is counted in exactly one bucket.
- `at_risk_units` = sum over student courses whose best finding is at-risk.
- `no_articulation_units` = sum over `no_articulation` findings.
- `still_owed_units` = sum over `still_owed` findings' units.
- Dollar fields: doc "Cost table" below; None when the target institution has no cost row.

## `transfer/costs.py` and `data/curated/costs.json`

`costs.json` is curated committed data with source URLs; NUMBERS ARE A USER GATE: the executor fills figures only from sources the user confirms in-session (overview doc, "Permission gates"); no invented numbers, including the well-known California CC per-unit fee, which still needs a dated source URL.

Locked file shape:

```json
{
  "version": "costs-v1",
  "sources": [{"url": "...", "note": "...", "retrieved": "2026-08-.."}],
  "cc_per_unit_default": 0.0,
  "target_per_unit": {"7": 0.0, "39": 0.0, "117": 0.0, "120": 0.0}
}
```

`transfer/costs.py`: a frozen `CostTable` model (`FROZEN`, fields mirroring the file, all rates `ge=0`) with `load_cost_table(path) -> CostTable`; it is transfer-local, not a `contracts/` wire contract, because only `transfer/` consumes it (no spec doc; the module docstring records this decision).
Dollar computation, locked: `at_risk_dollars = at_risk_units * target_per_unit[receiving_id]` and `no_articulation_dollars = no_articulation_units * target_per_unit[receiving_id]`, rounded to 2 places; missing target row -> both None.
Rationale, recorded for the write-up: lost or risky units must be retaken at the TARGET's per-unit price, so the target rate is the honest cost of a lost credit.

## `transfer/triage.py`

`TriageBoard` frozen view-model: `columns: dict[TriageBucket, tuple[Finding, ...]]` in evaluator order, `still_owed: tuple[Finding, ...]`, `header: TriageHeader` frozen (`clean_units`, `at_risk_units`, `no_articulation_units`, `still_owed_units`, `at_risk_dollars`, `no_articulation_dollars`, `course_count`, `finding_count`).
`build_triage_board(evaluation: Evaluation) -> TriageBoard`: a pure projection; no re-sorting beyond the evaluator's locked order, no PRNG, no clock (frontend-determinism axiom; `lib/evaluation.ts` mirrors this shape in Week 2).

## `backend/scripts/evaluate_student.py` (the Week 1 milestone CLI)

Flags: `--db data/articulation.db`, `--student data/curated/demo_students/deanza_ucsd_cs.json`, `--sending 113`, `--receiving 7`, `--major-key <assist key>`.
Flow: load the bundle through `assist/store.py` read surface, resolve the student file's courses against `cc_courses` (exact match only at this increment; fuzzy arrives with increment 7), build the evaluation, print the triage board as plain text with citations.

`data/curated/demo_students/deanza_ucsd_cs.json`, locked shape: `{"version": "demo-student-v1", "comment": "...", "courses": [{"course_code": "...", "units": 5.0}]}`.
Locked composition criteria (exact list finalized in split S10b against the built db and recorded in `docs/notes/evaluator_verification.md`): 8-10 De Anza courses producing at least one finding in every bucket: the honors-or-regular clean matches (MATH 1A, MATH 1B, MATH 2A, CIS 22C, CIS 36B), exactly one half-series (MATH 1C without MATH 1D -> `partial_series` on MATH 20C/20E), and one projection course that articulates to a different corridor target but not UCSD (`no_articulation`; pickable only after the S9c corridor build).

## Tests

`backend/tests/transfer/` with fixture scenarios in `backend/tests/fixtures/transfer/`, one JSON file per case: `{"comment": ..., "bundle": {...}, "student_courses": [...], "expected_findings": [{"code": ..., "bucket": ..., "student_course_codes": [...], "receiving_course_code": ..., "units": ...}]}` (expected entries compared on those five fields plus citation presence).

One named scenario per `EvaluationFindingCode` (testing-strategy requirement): `transfers_clean.json`, `advisement_note.json`, `partial_series.json`, `fuzzy_match.json`, `stale_year.json`, `no_articulation.json`, `still_owed.json`, `double_count_risk.json`, `unresolved.json`.
Edge scenarios from the roadmap's list: `note_only_articulation.json` (all-notes expression stays unsatisfied, receiving course goes still-owed), `no_course_articulated_cell.json` (`sending_expr` null), `or_requirement_group.json` (the CSE 15L / CSE 29 shape: neither satisfied -> one still-owed finding with the `or` detail; one satisfied -> no finding), `honors_tiebreak.json` (both `AnyOf` branches satisfied -> earliest index wins, matched codes prove it).

Direct unit tests for `evaluate_expr` (mandatory per `CLAUDE.md` testing requirements): every leaf/group state case above, partial-series arithmetic, note collection on `all` vs chosen-branch-only on `any`, determinism (two calls deep-equal), and depth-3 trees from the articulation_expr valid fixtures.
Units and dollars: hand-computed `UnitsSummary` values per scenario; a course counted in exactly one bucket when it appears in both a clean and an at-risk articulation; dollar rounding; missing cost row -> None.
Triage: purity (two calls on the same evaluation deep-equal), order preservation, header totals equal the summary.
CLI: run against a temp db built from the captured fixtures (doc 02 store), assert the demo shape renders and exits 0.

## Exit criteria (the Aug 6 milestone)

- `make check` green; one named fixture per finding code proven.
- The curated demo student evaluates at the CLI against the demo pair; every finding hand-verified against the live assist.org agreement and recorded in `docs/notes/evaluator_verification.md` (S10b).
- Units and dollar totals verified by hand against the curated cost table.

## Amendment, 2026-08-02 (S10a): reconciling this plan with the S9d/S9e artifact

This doc was authored 2026-07-31 against contracts that no longer exist in that shape.
The S9d/S9e splits added `ReceivingSeries` (42,242 stored articulations, 12% of the artifact), made `TemplateCell.course` nullable in favour of a course-or-series choice, added `RequirementGroupAsset.select_courses` (26,121 stored groups), and populated advisements at volume (19,149 articulations, 48,249 groups).
The sections above are left as written (history is not rewritten); where this amendment contradicts them, the amendment wins.
Every semantics decision below that the specs did not already lock was made by the user on 2026-08-02, not by an executor.

### Series receiving sides in classification

Step 2 is unchanged: every articulation with a non-null `sending_expr` is evaluated, series rows included, since the sending side is one expression either way.
Step 3's finding fields change for a series articulation, because `Articulation.receiving_course` is None there:

- `receiving_course_code` = None (a sequence has no single code; the `Finding` contract already allows this).
- `receiving_course_title` = `receiving_series.name`, ASSIST's own rendering, verbatim (the normalizer already stripped it).
- Everything else (units from matched student courses, citation, the at-risk priority chain) is unchanged.

The locked ordering key in step 8 is unchanged; a series finding contributes `""` for `receiving_course_code or ""`, and ties beyond the key preserve evaluation order because every sort in the evaluator must be stable (Python's `sorted` is; do not replace it with a non-stable sort).

### Series template cells in still-owed

Step 7's cell-satisfaction join (`template_cell_id == cell.cell_id`, expression `satisfied`, notes do not block) is unchanged and applies to series cells identically.
What changes is cell units and cell display, since `TemplateCell.course` may be None:

- `cell_units(cell)` = `course.units_min` for a course cell; for a series cell, the sum of the series courses' `units_min` when `conjunction == "And"`, and the MINIMUM over the series courses' `units_min` when `conjunction == "Or"` (user decision: the cheapest honest completion, mirroring this doc's locked Or-section rule; 380 stored Or-series exist).
- `cell_label(cell)` = the course code for a course cell, `series.name` for a series cell; labels are used in `detail` enumerations.
- A still-owed finding whose single owed cell is a series carries `receiving_course_code` = None and `receiving_course_title` = `series.name`.

### `select_courses` groups: satisfaction and the still-owed line

Group satisfaction is now three-way (the first two are this doc's original rules):

- `conjunction == "And"`: every section satisfied (every cell satisfied).
- `conjunction == "Or"`, `select_courses` None: at least one section fully satisfied.
- `select_courses == N`: at least N SATISFIED cells across the union of the group's sections, one pool; a satisfied series cell counts as one (locked in `docs/specs/agreement.schema.md` and spotchecks section 11).

A `partial` expression outcome contributes NOTHING to any of the three: not to section completion, not to the pool count (user decision).
The partial surfaces exclusively as its at-risk `partial_series` finding, and the cell still counts as owed.

An unsatisfied `select_courses` group emits ONE still-owed finding (user decision), never one per owed cell:

- `detail` = `complete {K} more from: {labels}` where `K = select_courses - satisfied_cell_count` and the labels are the owed cells' `cell_label`s in template order (sections by `position`, cells in list order), joined by `" or "`.
- Enumeration cap, locked: at most 8 labels; when more cells are owed, append `" or {remaining} more options"`.
  Pools run 2 to 33 cells in the corridor and `Finding.detail` caps at 500 characters; the cap is deterministic and applied by count, not by character length.
- `units` = the sum of the K SMALLEST owed-cell `cell_units` values (user decision: the cheapest completion, deterministic; ties broken by template order).
- `receiving_course_code`/`title` follow the existing rule: set only when exactly one cell is owed.
- `citation` follows the existing rule: the first owed cell's articulation position when one exists, else position 0.

For `And` groups the owed units stay "sum of owed cells' `cell_units`", and for plain `Or` groups "minimum over sections of that section's owed-cell `cell_units` sum", both now series-aware via `cell_units`.

### Advisements at volume: the downgrade stands, group texts ride still-owed

Measured 2026-08-02 against the committed artifact, because this doc's advisement rules were written when advisements were rare:

- The step 3 at-risk trigger (articulation `advisements` plus path notes) fires on 29,954 of 323,848 expr-bearing articulations (9.2%); the demo pair carries exactly 2 such rows.
  The board does not drown; the downgrade chain in step 3 stands exactly as written.
- `RequirementGroupAsset.advisements` (48,249 groups, including the 41,246 flattened cell-level grade minimums) is read by NOTHING in this doc's algorithm.
  User decision: an owed group's advisements are carried on its still-owed finding's `advisements` field; a SATISFIED group's advisements do not create or downgrade findings in this increment, and their surfacing is deferred to the Week 2 triage-board group rendering.
  Recorded consequence, deliberately accepted: until Week 2 lands, a satisfied group's grade-minimum text is not visible in the findings object; 48.4% of matched cell-bound articulations sit in such groups, and downgrading them all was rejected as drowning the board.

### S10b addendum, 2026-08-02: board-shape decisions, recorded rather than silent

Made during split S10b; the re-deferral was confirmed by the user in-session, the other two are executor interpretations recorded here so nothing about the board shape is decided silently.

- A SATISFIED group's advisements stay out of the findings object AND out of `TriageBoard`: `triage.py` is the first consumer that could have surfaced them, and the surfacing is explicitly re-deferred to the Week 2 board rendering (user confirmation, 2026-08-02).
  The locked `TriageBoard` shape has no slot for them, and adding one here would widen a locked view-model mid-split.
- `TriageBoard.columns` holds the three CREDIT buckets (`transfers_clean`, `at_risk`, `no_articulation`) and `still_owed` is its own field, because this doc lists both fields and duplicating the still-owed findings into a fourth column would make one of them redundant; still-owed findings describe requirements, not the student's credits.
  Together the four cover every finding exactly once, which `test_board_partitions_findings_in_evaluator_order` pins.
- A course articulating in both the major and a dept agreement keeps ONE FINDING PER ARTICULATION on the board (this doc's step 3 emits per-articulation by design); grouping them is deferred with the rest of the Week 2 board rendering, not done silently here.
- The CLI takes a `--costs` flag beyond this doc's flag list, defaulting to `data/curated/costs.json` when that file exists, because the exit criteria require dollar totals and the cost-table location must be explicit.

### `templateOverrides`: closed, no evaluator impact

Spotchecks section 12 (2026-08-02) proves ASSIST's renderer ignores `templateOverrides` entirely: the variant join does not exist anywhere in the public API surface, the SPA bundle maps and never consumes the field, and both rendered checks show the default rule.
The stored `sending_expr` IS the rendered rule for all 352,024 rows, including the 1,689 override-carrying ones.
No contract change, no rebuild, no evaluator handling, and hand-verification needs no override avoidance.
