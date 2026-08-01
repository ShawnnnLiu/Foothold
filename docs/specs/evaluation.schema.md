# evaluation

Canonical module: `backend/src/starmap/contracts/evaluation.py`.

The findings object: the complete deterministic answer to "what happens to my credits at this university, for this major, this year".

It is load-bearing twice over.
It is the wire shape of `POST /api/evaluations` in Week 2, and it is the vocabulary gate, second half: the findings object handed to the petition prompt IS the object the citation validator checks the drafted letter against.
One projection, two consumers.
A letter may only cite what a finding already carries, so anything the letter is allowed to say must be a field here, and anything not here is by construction unciteable.

Everything in this module is produced by deterministic code (`transfer/evaluate.py`, increment 6).
No LLM output ever enters it; `detail` is deterministic template text.

The evaluation ALGORITHM - classification order, units attribution, and the finding sort key - is locked in `docs/implementation-plans/articulation/03-transfer-evaluator.md`.
This spec covers only the shape and the invariants a consumer may rely on.

## StudentCourse

One resolved input course.
Unresolved input never becomes a `StudentCourse`: it becomes an `unresolved` finding instead, so this list is exactly the set of courses the evaluator actually reasoned about.

| Field | Type | Constraints |
| --- | --- | --- |
| `course_code` | str | Normalized via `normalize_course_code`. |
| `title` | str \| None | Default `None`; 1..300 chars, control-character hygiene. |
| `units` | float | `gt=0`, `le=20`. |
| `resolution` | `Literal["exact", "fuzzy_match"]` | How the input resolved against the `cc_courses` projection. |

`resolution` is carried per course rather than recomputed at finding time because it is an input-provenance fact: a finding downgraded to at-risk by `fuzzy_match` must be able to name which course was matched loosely, and the UI shows the student what it guessed.

`title` is optional because a pasted transcript line may resolve to a code without a usable title, and inventing one would be fabrication.

## Citation

The ground-truth pointer every finding that can carry one does carry.
The citation axiom is the reason this model exists as a required nested object rather than three loose fields: a partial citation is not a citation.

| Field | Type | Constraints |
| --- | --- | --- |
| `assist_key` | str | The agreement-key pattern from `agreement.ASSIST_KEY_PATTERN`. |
| `position` | int | `ge=0`; the articulation's index in the decoded `articulations` array. |
| `year_label` | str | Year-label pattern plus the consecutive-years rule. |

`assist_key` rather than the derived `agreement_id`, because the key is what a human can paste into assist.org to check the claim; a 16-hex-character derived id verifies nothing for the student reading the petition letter.

The consecutive-years rule is the single function `agreement.check_consecutive_years`, shared with `Agreement.academic_year_label`.
Two copies of a rule this small is exactly how a citation and the agreement it cites drift into disagreeing.

## Finding

| Field | Type | Constraints |
| --- | --- | --- |
| `code` | EvaluationFindingCode | |
| `bucket` | TriageBucket | Must equal `BUCKET_FOR_CODE[code]`. |
| `student_course_codes` | list[str] | Default empty; each normalized; case-insensitively unique. |
| `receiving_course_code` | str \| None | Default `None`; normalized when present. |
| `receiving_course_title` | str \| None | Default `None`; 1..300 chars, control-character hygiene. |
| `units` | float | `ge=0`; the units attributed to this finding (attribution rules in doc 03). |
| `citation` | Citation \| None | Default `None`; required or forbidden by `code`, see below. |
| `advisements` | list[str] | Default empty; each 1..2000 chars with control-character hygiene. |
| `detail` | str \| None | Default `None`; 1..500 chars, control-character hygiene; deterministic template text. |

`bucket` is stored rather than derived at render time so the wire shape is self-describing for the frontend, and validated against `BUCKET_FOR_CODE` so storing it cannot make it a second source of truth.

`student_course_codes` may be empty: a `still_owed` finding is about a requirement no course was applied to.
`units` may be 0 for the same reason, and for an `unresolved` finding whose request carried no unit count.

These codes are deliberately NOT constrained to be a subset of `Evaluation.student_courses`.
An `unresolved` finding names a course that failed resolution and therefore never became a `StudentCourse`, so a subset validator would reject exactly the finding the student most needs to see.

### Finding validators

| Validator | Rule |
| --- | --- |
| bucket derivation | `bucket == BUCKET_FOR_CODE[code]`; the error quotes both. |
| student-course uniqueness | `find_duplicates` over `student_course_codes`; the error names the duplicates. |
| citation requirement | Codes in `CODES_REQUIRING_CITATION` require a non-null `citation`; codes in `CODES_FORBIDDING_CITATION` require `citation` null. |
| advisement note | `code == advisement_note` requires a non-empty `advisements` list. |

Citation partition, normative (tests assert both halves and their totality):

| Set | Members | Why |
| --- | --- | --- |
| `CODES_REQUIRING_CITATION` | `transfers_clean`, `advisement_note`, `partial_series`, `fuzzy_match`, `stale_year`, `double_count_risk`, `still_owed` | Each is a claim about a specific published articulation, so it must point at one. |
| `CODES_FORBIDDING_CITATION` | `no_articulation`, `unresolved` | There is no articulation to cite; the pair context lives on the envelope. |

The two sets are disjoint and together cover every `EvaluationFindingCode`.
A new finding code therefore cannot be added without deciding which side it falls on: the totality test fails until it is classified, which is the point.

The `advisement_note` rule is the contract-level half of the never-silently-satisfied axiom.
A finding that claims an advisement exists while carrying no advisement text would strip the student of the only part they can act on.

## UnitsSummary

| Field | Type | Constraints |
| --- | --- | --- |
| `clean_units` | float | `ge=0`. |
| `at_risk_units` | float | `ge=0`. |
| `no_articulation_units` | float | `ge=0`. |
| `still_owed_units` | float | `ge=0`. |
| `at_risk_dollars` | float \| None | Default `None`; `ge=0` when present. |
| `no_articulation_dollars` | float \| None | Default `None`; `ge=0` when present. |

The dollar fields are nullable because the curated cost table (increment 6) may not carry a row for the target institution, and `None` is the honest answer there.
A zero would read as "this costs nothing", which is the opposite of "we do not know".

The four unit totals are deliberately NOT constrained to sum to the student's total units: doc 03's attribution rules assign each student course to exactly one bucket, but `still_owed_units` counts requirement units no student course covers, so a cross-total check would encode a false invariant.

## Evaluation

| Field | Type | Constraints |
| --- | --- | --- |
| `evaluation_id` | str | Pattern `^eval_[0-9a-f]{16}$`; minted via `IdGenerator.new_id("eval")`, not derived. |
| `sending_institution_id` | int | `gt=0`. |
| `receiving_institution_id` | int | `gt=0`. |
| `major_key` | str | The agreement-key pattern; the major agreement evaluated. |
| `dept_keys` | list[str] | Default empty; each the agreement-key pattern; case-insensitively unique. |
| `year_id` | int | `gt=0`. |
| `year_label` | str | Year-label pattern plus the consecutive-years rule. |
| `student_courses` | list[StudentCourse] | Min length 1; `course_code` values unique. |
| `findings` | list[Finding] | May be empty. |
| `units` | UnitsSummary | Required. |
| `created_at` | datetime | Timezone-aware. |

`evaluation_id` is minted, not content-derived, because two evaluations of the same inputs at different times are distinct events worth telling apart in the call log and the session store.

`findings` ORDER is produced deterministically by the evaluator (the sort key is locked in doc 03) but is deliberately not contract-enforced: a contract validator that re-checked the order would have to reimplement the evaluator's ranking, which is a second source of truth for the exact thing the evaluator owns.
The order-stability axiom is tested at the evaluator and view-model layers instead.

Two further checks are deliberately absent, for the same one-source-of-truth reason:

- Key/category coherence (`major_key` naming a `Major` segment, `dept_keys` naming `Department` segments) is already enforced on `Agreement`, and these keys are copied from validated `Agreement` rows by the composition root.
- Citation/envelope agreement (every `Finding.citation.assist_key` being `major_key` or one of `dept_keys`) would duplicate the evaluator's bundle construction inside the contract.

### Evaluation validators

| Validator | Rule |
| --- | --- |
| institutions differ | `sending_institution_id != receiving_institution_id`; the error quotes the shared value. |
| `dept_keys` uniqueness | `find_duplicates`; the error names the duplicates. |
| `student_courses` uniqueness | `find_duplicates` over the course codes; the error names the duplicates. |
| `year_label` consecutive years | The shared `check_consecutive_years`. |
| `created_at` timezone-aware | Naive datetimes are rejected, quoting the ISO value. |

## Fixtures

Valid:

| Fixture | What it pins |
| --- | --- |
| `minimal.json` | The smallest legal evaluation: one student course, one `transfers_clean` finding with its citation, a units summary with null dollars. |
| `demo_shape.json` | One finding of every `EvaluationFindingCode` with its correct bucket and its citation present or absent per the partition. This is the reference shape for the increment-6 evaluator and the Week 2 petition citation validator, and the test suite asserts it covers the enum exhaustively, so a new code cannot ship without an example. |

`demo_shape.json` is built on the real De Anza to UC San Diego demo pair: its course codes, titles, and unit counts are transcribed from the captured agreements, and its `stale_year` finding cites a prior-year department key so the citation-predates-the-envelope case has an example.
Every citation position is the receiving course's real index in its capture (MATH 20A at major position 5, MATH 20B at 1, MATH 20E at 3, CSE 12 at 7, MATH 15A at department position 4), except the `still_owed` finding.
That one cites position 0 on purpose: it owes CSE 15L or CSE 29, the two template cells the major capture publishes with no articulation entry at all, which is doc 03's "else position 0" branch where the agreement key and year carry the citation.
Its two dollar figures are arithmetic at a round placeholder rate of 100 per unit, NOT a cost claim: the real per-unit figures are a user-gated curated input in increment 6 (`docs/implementation-plans/articulation/00-overview.md`, permission gates), and no invented number may reach `data/curated/costs.json`.
`test_demo_shape_is_laid_out_in_evaluator_order` pins the finding order to doc 03's sort key even though the contract does not enforce order, so the reference shape stays a faithful model of what the evaluator will emit.

Invalid: `bad_evaluation_id`, `institution_id_zero`, `same_institutions`, `bad_major_key`, `bad_dept_key`, `duplicate_dept_keys`, `year_id_zero`, `bad_year_label`, `nonconsecutive_year_label`, `empty_student_courses`, `duplicate_student_courses`, `student_bad_course_code`, `student_units_zero`, `student_units_above_max`, `student_title_control_char`, `bad_resolution`, `bucket_code_mismatch`, `citation_missing_for_clean`, `citation_present_for_unresolved`, `advisement_note_without_advisements`, `finding_duplicate_course_codes`, `finding_bad_receiving_code`, `finding_title_control_char`, `negative_finding_units`, `detail_control_char`, `bad_citation_key`, `negative_citation_position`, `nonconsecutive_citation_year_label`, `negative_units_summary`, `negative_dollars`.

Doc 01 locks ten of these; the remaining twenty exist because the exit criteria require a named fixture per constraint and validator, and this module carries five models' worth of both.
The one constraint family without its own fixture here is `advisements`, which reuses the `AdvisementText` alias from `contracts/articulation.py`; `articulation/advisement_control_char` and `articulation/advisement_too_long` already prove that alias's length and hygiene rules fire.
