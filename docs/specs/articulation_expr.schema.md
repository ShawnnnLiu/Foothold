# articulation_expr

Canonical module: `backend/src/starmap/contracts/articulation_expr.py`.

Recursive discriminated union `ArticulationExpr = AllOf | AnyOf | CourseLeaf | NoteLeaf`.
This is the sending-side expression of an ASSIST articulation: what the student must have completed at the community college for a receiving course to be satisfied.
The members are structurally discriminated by their distinct required keys (`all`, `any`, `course`, `note`); dispatch is owned by `parse_articulation_expr(data) -> ArticulationExpr` in the same module.
Consumers type fields as the union with a `BeforeValidator` calling `parse_articulation_expr` (see `Articulation.sending_expr`).
`ArticulationExprRoot` is the `RootModel` wrapper registered as the `articulation_expr` generated schema.

Generalized from the pre-pivot `prereq_expr` contract on 2026-07-31.
The structure, depth rule, and dispatch are unchanged; the two deltas are recorded under Fields below.

## Fields

### CourseLeaf

| Field | Type | Constraints |
| --- | --- | --- |
| `course` | str | Normalized via `normalize_course_code`; must match `COURSE_CODE_RE`. |

Delta from `prereq_expr`: the `equivalent_ok` field is gone.
It encoded a Columbia bulletin idiom ("or an equivalent course"); in ASSIST, equivalence is not a property of a leaf but the substance of the articulation itself, which already names the exact accepted sending courses.

### NoteLeaf

| Field | Type | Constraints |
| --- | --- | --- |
| `note` | str | 1..2000 chars; control-character hygiene (codepoints below 0x20 other than `\n\r\t` rejected, reported as `U+XXXX`). |

Delta from `prereq_expr`: the cap widens from 500 to 2000 characters.
ASSIST advisement prose is the note-leaf source, and its real length is unverified: every `attributes` list in the captured fixtures is empty, so the shape is fixture-pending (`docs/implementation-plans/articulation/00-overview.md`, "Advisements are fixture-pending").
2000 is the same cap carried by `Articulation.advisements` and `Finding.advisements`, so an advisement text can move between those fields and a note leaf without a length surprise.

A `note` leaf is never silently satisfied by the evaluator: it downgrades a match to at-risk and is always surfaced (axiom).

### AllOf

| Field | Type | Constraints |
| --- | --- | --- |
| `all` | list[ArticulationExpr] | Min length 1. |

### AnyOf

| Field | Type | Constraints |
| --- | --- | --- |
| `any` | list[ArticulationExpr] | Min length 1. |

## Validators

| Validator | Rule |
| --- | --- |
| `NoteLeaf.note` control-char check | Rejects control codepoints, naming the offending `U+XXXX`. |
| `CourseLeaf.course` normalization | Uppercase, whitespace-collapse, strip, then pattern check; invalid input is named in the error. |
| Depth check on `AllOf` and `AnyOf` | Nesting depth <= 3, where a bare leaf is depth 1 and each group level adds 1; the error message quotes the offending depth. |
| `parse_articulation_expr` dispatch | A mapping with none of the four discriminating keys is rejected with a message listing them. |

## Serialization

Serialization must round-trip the plan's example verbatim (`model_dump(mode="json", exclude_defaults=True)` of the parsed example equals the example object).
That example is the valid fixture `plan_example.json`.

## Example

The plan's sending-side example, "MATH 1A and MATH 1B, or the honors series" (`docs/STARMAP_PATHFINDERS_PLAN.md`):

```json
{"any": [
  {"all": [{"course": "MATH 1A"}, {"course": "MATH 1B"}]},
  {"all": [{"course": "MATH 1AH"}, {"course": "MATH 1BH"}, {"note": "honors series must be completed entirely"}]}
]}
```
