# prereq_expr

Canonical module: `backend/src/starmap/contracts/prereq_expr.py`.

Recursive discriminated union `PrereqExpr = AllOf | AnyOf | CourseLeaf | NoteLeaf`.
The members are structurally discriminated by their distinct required keys (`all`, `any`, `course`, `note`); dispatch is owned by `parse_prereq_expr(data) -> PrereqExpr` in the same module.
Consumers type fields as the union with a `BeforeValidator` calling `parse_prereq_expr` (see `Course.prereq_expr`).
`PrereqExprRoot` is the `RootModel` wrapper registered as the `prereq_expr` generated schema.

## Fields

### CourseLeaf

| Field | Type | Constraints |
| --- | --- | --- |
| `course` | str | Normalized via `normalize_course_code`; must match `COURSE_CODE_RE`. |
| `equivalent_ok` | bool | Defaults to `false`. |

### NoteLeaf

| Field | Type | Constraints |
| --- | --- | --- |
| `note` | str | 1..500 chars; control-character hygiene (codepoints below 0x20 other than `\n\r\t` rejected, reported as `U+XXXX`). |

### AllOf

| Field | Type | Constraints |
| --- | --- | --- |
| `all` | list[PrereqExpr] | Min length 1. |

### AnyOf

| Field | Type | Constraints |
| --- | --- | --- |
| `any` | list[PrereqExpr] | Min length 1. |

## Validators

| Validator | Rule |
| --- | --- |
| `NoteLeaf.note` control-char check | Rejects control codepoints, naming the offending `U+XXXX`. |
| `CourseLeaf.course` normalization | Uppercase, whitespace-collapse, strip, then pattern check; invalid input is named in the error. |
| Depth check on `AllOf` and `AnyOf` | Nesting depth <= 3, where a bare leaf is depth 1 and each group level adds 1; the error message quotes the offending depth. |
| `parse_prereq_expr` dispatch | A mapping with none of the four discriminating keys is rejected with a message listing them. |

## Serialization

Serialization must round-trip the plan's example verbatim (`model_dump(mode="json", exclude_defaults=True)` of the parsed example equals the example object).
That example is the valid fixture `plan_example.json`.

## Example

```json
{"all": [
  {"any": [{"course": "COMS W3134"}, {"course": "COMS W3136"}, {"course": "COMS W3137"}]},
  {"course": "COMS W3203", "equivalent_ok": true},
  {"note": "or instructor permission"}
]}
```
