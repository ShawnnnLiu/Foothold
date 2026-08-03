# arbitrage

Canonical module: `backend/src/starmap/contracts/arbitrage.py`.

One Mode B row: a set of community-college courses the student has not taken, the receiving requirement they would articulate back to, and the tuition delta of taking them at the community college instead.
The wire shape of `GET /api/arbitrage` (frontend implementation plan doc 04); the list order is produced by `transfer/arbitrage.py` and is server truth, never re-sorted client-side.

Everything in this module is produced by deterministic code (`transfer/arbitrage.py`).
No LLM anywhere in Mode B: candidacy is recomputed with `evaluate_expr` over the evaluation's resolved course set, never parsed out of findings text.

The ranking ALGORITHM - the candidate set, the units accounting, the savings formula, and the sort key - is locked in `docs/implementation-plans/frontend/04-arbitrage.md`.
This spec covers only the shape and the invariants a consumer may rely on.

## ArbitrageRow

| Field | Type | Constraints |
| --- | --- | --- |
| `missing_course_codes` | list[CourseCode] | Min length 1; each normalized; case-insensitively unique. The CC courses to take. |
| `receiving_course_code` | CourseCode \| None | Default `None`; normalized when present. |
| `receiving_course_title` | str \| None | Default `None`; 1..300 chars, control-character hygiene. |
| `receiving_series_name` | str \| None | Default `None`; 1..300 chars, control-character hygiene. ASSIST's own series rendering, verbatim. |
| `units` | float | `gt=0`; the receiving cell's units. |
| `savings_dollars` | float \| None | Default `None`; `None` when the target has no per-unit rate, never zero. |
| `citation` | Citation | Required; reuses `evaluation.Citation`. |

`missing_course_codes` holds only the expression's missing course leaves: a partial series emits the unfinished members, not the whole series, because the finished ones are not purchasable.

`receiving_course_code` and `receiving_series_name` mirror the `Articulation` receiving side: a series receiving requirement has no single course code, so exactly one of the two is populated.
`receiving_course_title` rides with the course code and is `None` for a series row; the series name is the display string there, quoted from the agreement rather than rebuilt from parts.

`savings_dollars` is nullable because the curated cost table may carry no per-unit rate for the target (flat-fee summer campuses publish none), and `None` is the honest answer there.
A zero would read as "this saves nothing", which is the opposite of "we do not know".
The engine surfaces such rows after all dollar rows and counts them in `omitted_no_rate` instead of dropping them.

`citation` is required with no code-conditional partition: Mode B never emits an uncited row.
Every candidate IS a published major-agreement articulation, so the pointer (agreement key, articulation position, year) always exists.

### ArbitrageRow validators

| Validator | Rule |
| --- | --- |
| missing-course uniqueness | `find_duplicates` over `missing_course_codes`; the error names the duplicates. |
| exactly one receiving side | Exactly one of `receiving_course_code` and `receiving_series_name` is non-null; the error quotes which are set. |
| title rides with the code | `receiving_course_title` non-null requires `receiving_course_code` non-null. |

## Fixtures

Valid:

| Fixture | What it pins |
| --- | --- |
| `dollar_row.json` | A course-receiving row with a savings figure, the common shape. |
| `no_rate_row.json` | `savings_dollars` null with everything else populated: the no-per-unit-rate target. |
| `series_row.json` | A series-receiving row: `receiving_series_name` set, code and title null, multiple missing courses. |

Invalid: `empty_missing_course_codes`, `duplicate_missing_course_codes`, `both_receiving_sides`, `title_without_code`, `negative_units`, `missing_citation`.

The control-character and length rules on the two title-ish fields reuse the shared `reject_control_chars` hygiene already proven by the `evaluation` and `articulation` fixture suites, so they carry no dedicated fixtures here (same reasoning as `evaluation`'s reuse of `AdvisementText`).
