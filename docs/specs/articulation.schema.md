# articulation

Canonical module: `backend/src/starmap/contracts/articulation.py`.

One row of an ASSIST agreement: a receiving course, and the sending-side expression a student must satisfy for it.
This is the unit the deterministic evaluator consumes and the unit every finding cites, so it carries its own citation coordinates (`agreement_id`, `position`) rather than relying on ambient context.

The module also owns two pattern constants and one text alias that `contracts/agreement.py` imports (`AGREEMENT_ID_PATTERN`, `GUID_PATTERN`, `AdvisementText`).
They live here, not in `agreement.py`, because doc 01 locks the import direction as agreement -> articulation (`TemplateCell.course` is a `ReceivingCourse`); a single home in the imported-from module keeps the regexes from drifting across two files without an import cycle.

Field shapes are derived from the captured `agreement_major_cse_cs_113_to_7_y76.json` and `agreement_dept_math_113_to_7_y76.json`.
This contract holds the NORMALIZED row; the double-decode, the template-cell dispatch, and the expression-building algorithm are locked in `docs/implementation-plans/articulation/02-assist-fetch-normalize-store.md`.

## ReceivingCourse

The receiving-side course object, shared by `Articulation.receiving_course` and `agreement.TemplateCell.course`.

| Field | Type | Constraints |
| --- | --- | --- |
| `course_code` | str | Normalized via `normalize_course_code`; must match `COURSE_CODE_RE`. |
| `prefix` | str | 1..16 chars, pattern `^[A-Z][A-Z0-9&/. \-]{0,15}$`. |
| `number` | str | 1..8 chars, pattern `^[A-Z0-9.\-]{1,8}$`. |
| `title` | str | 1..300 chars; control-character hygiene. |
| `units_min` | float | `gt=0`, `le=20`. |
| `units_max` | float | `le=20`. |

`prefix` and `number` are kept alongside the derived `course_code` because ASSIST publishes them separately and the UI displays them separately; storing only the joined code would force a lossy re-split.
Their two patterns are the constants `COURSE_PREFIX_PATTERN` and `COURSE_NUMBER_PATTERN` in `contracts/codes.py`, hoisted there during S8c when `cc_course` and `target_course` became the second and third models storing the same split pair.

`title` is accepted verbatim, including surrounding whitespace: the major capture publishes CSE 29 as `"Systems Programming and Software Tools "` with a trailing space.
The contract does not strip it, because a title strip is a normalization decision and `assist/normalize.py` owns normalization; recorded here so increment 5 strips it rather than shipping the gap into the UI.

### ReceivingCourse validators

| Validator | Rule |
| --- | --- |
| `title` control-char check | Rejects codepoints below 0x20 other than `\n\r\t`, naming the offending `U+XXXX`. |
| units range | `units_max >= units_min`; the error quotes both values. |
| code derivation | `course_code == course_code_from_parts(prefix, number)`; the error quotes all three values. |

The derivation check is the structural guarantee that the projection consumed by the evaluator, the FTS index, and the petition validator cannot disagree with the payload it came from.
`course_code_from_parts` is the single derivation in `contracts/codes.py`, so a code that fails to normalize raises there and is named in the error.

## Articulation

| Field | Type | Constraints |
| --- | --- | --- |
| `agreement_id` | str | Pattern `^agr_[0-9a-f]{16}$`. |
| `position` | int | `ge=0`; the entry's index in the decoded `articulations` array. |
| `template_cell_id` | str \| None | GUID pattern `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$` when present; default `None`. |
| `receiving_course` | ReceivingCourse | Required. |
| `sending_expr` | ArticulationExpr \| None | Default `None`; parsed through `parse_articulation_expr`. |
| `no_articulation_reason` | str \| None | Default `None`; 1..500 chars, control-character hygiene. |
| `advisements` | list[str] | Default empty; each entry 1..2000 chars with control-character hygiene. |

`position` is a citation coordinate, not an ordering hint: the findings axiom requires every finding to name the agreement key, the articulation position, and the year, so the position must survive from the payload into the evaluation.

`template_cell_id` is `None` for department agreements (the base model has no template) and the cell GUID for major agreements.
It is the join key back to `agreement.TemplateCell.cell_id`; a template cell with no articulation carrying its id means "no articulation published for this cell" (CSE 15L and CSE 29 in the major capture).

`sending_expr` is `None` for "No Course Articulated", which ASSIST encodes two ways that mean the same thing: `sendingArticulation: null` (MATH 10B and MATH 10C in the department capture) and a present `sendingArticulation` with empty `items`.

`advisements` carries articulation-level and sending-articulation-level advisement text.
Group-level and course-level advisement text becomes `note` leaves INSIDE `sending_expr` instead, because those texts qualify a specific branch of the expression and lose their meaning when hoisted.
Both paths run through `advisement_texts` in `assist/normalize.py`, which is fixture-pending: every `attributes` list in the captures is empty, so a non-empty one raises `advisement_shape_unknown` rather than guessing a shape.
Nothing anywhere silently satisfies, drops, or paraphrases an advisement.

Payload fact recorded here during S8b, found by `test_assist_fixture_alignment.py` and not in the spike doc: on the two department rows whose `sendingArticulation` is null (MATH 10B and MATH 10C), all three articulation-level attribute lists (`attributes`, `courseAttributes`, `receivingAttributes`) are themselves `null` rather than `[]`.
Everywhere else, at all four levels, they are `[]`.
`advisement_texts` is specified over a list, so increment 5 must treat `null` as "no advisements" while still raising `advisement_shape_unknown` on a non-empty list; a bare truthiness check would collapse those two cases.

### Articulation validators

| Validator | Rule |
| --- | --- |
| reason excludes expression | `no_articulation_reason` non-null requires `sending_expr` null; the error quotes both. |

A reason for having no articulation cannot coexist with an articulation expression: the two states are contradictory, and an evaluator that saw both would have to pick one silently.

## Fixtures

Valid, transcribed from the captures (names carry provenance):

| Fixture | Source |
| --- | --- |
| `math20d_honors_or_regular.json` | Major capture index 0, MATH 20D: two single-course groups joined by one `Or` conjunction. |
| `math20e_and_series.json` | Major capture index 3, MATH 20E: one `And` group of MATH 1C + MATH 1D, no group conjunctions. |
| `math10b_no_articulation.json` | Department capture index 1, MATH 10B: `sendingArticulation: null`, so `sending_expr` is null and `template_cell_id` is null. |
| `synthetic_advisement.json` | Hand-built, NOT from a capture: a note leaf inside `sending_expr` plus an `advisements` entry, exercising the advisement mechanism while its ASSIST shape is still fixture-pending. Its text says so verbatim. |

Group ordering in the valid fixtures follows the locked normalizer rule (groups sorted by `position`), so `math20d_honors_or_regular` reads MATH 2A (position 0) before MATH 2AH (position 1) even though the payload array lists them the other way round.
Single-course groups stand alone as bare `course` leaves rather than one-element `all` groups, also per the locked rule.

Invalid: `reason_with_expr`, `bad_agreement_id`, `negative_position`, `bad_template_cell_guid`, `advisement_control_char`, `advisement_too_long`, `receiving_units_max_below_min`, `receiving_code_parts_mismatch`, `receiving_bad_course_code`, `receiving_bad_prefix`, `receiving_bad_number`, `receiving_title_control_char`, `receiving_units_min_zero`.
The six beyond doc 01's locked list cover constraint families that would otherwise have no fixture proving they fire, which the increment's exit criteria forbid.
