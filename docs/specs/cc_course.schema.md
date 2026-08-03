# cc_course

Canonical module: `backend/src/starmap/contracts/cc_course.py`.

One community-college course, projected out of the sending side of every stored agreement.

This projection is the vocabulary gate, first half: the rows UI autocomplete offers ARE the rows the transcript validator resolves against ARE the rows the FTS5 index is built from.
One projection, three consumers, never a re-derivation.
A course the student can pick but the validator cannot resolve, or the reverse, is the exact failure this single-projection rule exists to make impossible.

Field values are transcribed from the sending courses in the captured `agreement_major_cse_cs_113_to_7_y76.json` and `agreement_dept_math_113_to_7_y76.json`.
This contract holds the NORMALIZED row; the projection algorithm (walking every sending expression, deduplicating by `(institution_id, course_code)`, and raising `course_projection_conflict` on a conflicting duplicate) is locked in `docs/implementation-plans/articulation/02-assist-fetch-normalize-store.md`.

## Fields

| Field | Type | Constraints |
| --- | --- | --- |
| `institution_id` | int | `gt=0`; the ASSIST institution id of the community college this course belongs to. |
| `course_code` | str | Normalized via `normalize_course_code`; must match `COURSE_CODE_RE`. |
| `prefix` | str | 1..16 chars, pattern `COURSE_PREFIX_PATTERN`. |
| `number` | str | 1..10 chars, pattern `COURSE_NUMBER_PATTERN`. |
| `title` | str | 1..300 chars; control-character hygiene. |
| `units_min` | float | `gt=0`, `le=20`. |
| `units_max` | float | `le=20`. |

`institution_id` is a plain `gt=0` int rather than a foreign-key type because contracts do not carry referential integrity; the store enforces the join, and duplicating that check here would let a contract disagree with the database it came from.

`prefix` and `number` are kept alongside the derived `course_code` for the same reason `ReceivingCourse` keeps them: ASSIST publishes them separately and the UI displays them separately, so storing only the joined code would force a lossy re-split.

`units_min` and `units_max` are both kept even where they are equal in every captured row, because variable-unit community-college courses exist and the payload carries `minUnits`/`maxUnits` separately.

The pattern constants live in `contracts/codes.py`, imported by all three models that store the split pair (`ReceivingCourse`, `CcCourse`, `TargetCourse`).
`MAX_UNITS` lives in `contracts/articulation.py`, the module that first needed it, and is imported here for the same reason `agreement.py` imports its id patterns from `articulation.py`: one home per shared constant, no cycle.

## Validators

| Validator | Rule |
| --- | --- |
| `title` control-char check | Rejects codepoints below 0x20 other than `\n\r\t`, naming the offending `U+XXXX`. |
| units range | `units_max >= units_min`; the error quotes both values. |
| code derivation | `course_code == course_code_from_parts(prefix, number)`; the error quotes all three values. |

The code-derivation check is what makes the vocabulary gate structural rather than procedural: if a projection row's code could drift from its own prefix and number, autocomplete could offer a spelling the resolver would never match.

## Fixtures

Valid, transcribed from the captures (De Anza College, ASSIST institution 113):

| Fixture | Source |
| --- | --- |
| `math_1a.json` | MATH 1A, Calculus I, 5.0 units; the demo pair's most-cited sending course. |
| `stat_c1000h.json` | STAT C1000H, the letter-prefixed, honors-suffixed number that motivated the ASSIST-shaped regex. |
| `bus2_90_campus_suffix.json` | BUS2 90 F: a digit inside the prefix token AND a trailing campus-suffix token, the two shapes that cost 1,344 articulations before S9c widened the regex. |
| `cis_22c.json` | CIS 22C, 4.5 units; a non-integer unit count, which the dollar arithmetic in increment 6 must survive. |

Invalid: `institution_id_zero`, `bad_course_code`, `bad_prefix`, `bad_number`, `padded_number`, `title_empty`, `title_control_char`, `title_too_long`, `units_min_zero`, `units_above_max`, `units_max_below_min`, `code_parts_mismatch`.
`padded_number` is the one that proves the contract still refuses ASSIST's padded values (`"C1000H "`); the normalizer collapses them first, so a padded value reaching a contract means the normalizer stopped doing that.

Doc 01 locks five of these (`institution_id_zero`, `code_parts_mismatch`, `units_max_below_min`, `units_min_zero`, `title_empty`).
The other six are added because the increment's exit criteria require a named fixture proving every field constraint fires, and the code, prefix, number, title-length, title-hygiene, and unit-ceiling constraints would otherwise have none.
