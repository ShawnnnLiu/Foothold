# target_course

Canonical module: `backend/src/starmap/contracts/target_course.py`.

One receiving-institution course, projected out of the receiving side of every stored agreement.

It is the target-side counterpart of `cc_course`: the vocabulary for naming what a student still owes, what a finding points at, and what Mode B's arbitrage search inverts back onto community-college courses.

## Relationship to `CcCourse`

`TargetCourse` is field-for-field and validator-for-validator identical to `cc_course.CcCourse`.
That duplication is locked and deliberate: the house style has no contract inheritance, so a shared base class would be the only hierarchy in `contracts/` and would couple two projections that are free to diverge (a receiving-side row may later carry a UC-specific field a community-college row must never have).
The two module docstrings cross-reference each other, and `test_target_course.py` asserts the field sets and annotations still match, so the duplication cannot drift silently while it lasts.

Locked deviation from the plan's sketch: the plan showed a single `units` column, and this contract keeps `units_min`/`units_max` because the payload carries `minUnits`/`maxUnits` separately and variable-unit receiving courses exist in the wild.

## Fields

| Field | Type | Constraints |
| --- | --- | --- |
| `institution_id` | int | `gt=0`; the ASSIST institution id of the receiving university. |
| `course_code` | str | Normalized via `normalize_course_code`; must match `COURSE_CODE_RE`. |
| `prefix` | str | 1..16 chars, pattern `COURSE_PREFIX_PATTERN`. |
| `number` | str | 1..10 chars, pattern `COURSE_NUMBER_PATTERN`. |
| `title` | str | 1..300 chars; control-character hygiene. |
| `units_min` | float | `gt=0`, `le=20`. |
| `units_max` | float | `le=20`. |

## Validators

| Validator | Rule |
| --- | --- |
| `title` control-char check | Rejects codepoints below 0x20 other than `\n\r\t`, naming the offending `U+XXXX`. |
| units range | `units_max >= units_min`; the error quotes both values. |
| code derivation | `course_code == course_code_from_parts(prefix, number)`; the error quotes all three values. |

## Fixtures

Valid, transcribed from the captures (University of California, San Diego, ASSIST institution 7):

| Fixture | Source |
| --- | --- |
| `math_20d.json` | MATH 20D, Introduction to Differential Equations, 4.0 units; the receiving course of the major capture's index 0. |
| `cse_11.json` | CSE 11, whose 80-character title is the longest in either capture, sending or receiving, and the reason the 300-character cap is not tighter. |

Invalid: `code_parts_mismatch`, `units_max_below_min`.

This list is doc 01's locked pair and is deliberately shorter than `cc_course`'s.
The two models share an identical constraint set, `cc_course` ships a fixture proving each of those constraints fires, and the parity test proves the constraint sets are still identical; a second copy of all eleven fixtures would assert the same rules twice while doubling the maintenance cost of a future divergence.
What these two fixtures do prove is that the duplicated validators are actually wired into THIS model rather than inherited by accident.
