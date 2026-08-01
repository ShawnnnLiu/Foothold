# course

Canonical module: `backend/src/starmap/contracts/course.py`.

One catalog course as parsed from a bulletin department page.

Recorded decision (deviation from the plan's single `points` column): variable-point courses (research, independent study) are real, so the contract and the `courses` table carry `points_min` / `points_max`; fixed-point courses store the same value twice.

Recorded risk for increment 3: the bulletin contains `0.00 points` courses (e.g. `COMS E0001`, `ENGL UN2001`), which this contract rejects (`points_min > 0`).
The catalog build must either exclude them or this bound gets revisited with a spec update.

## Fields

| Field | Type | Constraints |
| --- | --- | --- |
| `course_code` | str | Normalized via `normalize_course_code`; must match `COURSE_CODE_RE`. |
| `title` | str | 1..300 chars; control-character hygiene. |
| `points_min` | float | > 0, <= 20. |
| `points_max` | float | <= 20; >= `points_min` (model validator). |
| `description` | str or null | 1..8000 chars when present; defaults to null. |
| `prereq_prose` | str or null | 1..4000 chars when present; defaults to null. |
| `prereq_expr` | PrereqExpr or null | Parsed via `parse_prereq_expr`; defaults to null. |
| `prereq_confidence` | literal | One of `parsed`, `fallback_flat`, `none`. |
| `bulletin_url` | str | Non-empty; must start with `http://` or `https://`. |
| `department_code` | str | 1..8 chars, uppercase letters only (`^[A-Z]+$`). |

## Validators

| Validator | Rule |
| --- | --- |
| `title` control-char check | Rejects control codepoints, reported as `U+XXXX`. |
| `bulletin_url` scheme check | Must be http or https; the offending value is quoted. |
| `points` cross-field | `points_max >= points_min`; the message names both fields and quotes both values. |
| `prereq_confidence` cross-field | `prereq_confidence == "none"` iff `prereq_expr` is null; `parsed` / `fallback_flat` require a non-null expr; messages name both fields. |

## Example

```json
{
  "course_code": "COMS W4701",
  "title": "Artificial Intelligence",
  "points_min": 3.0,
  "points_max": 3.0,
  "description": "Provides a broad understanding of the basic techniques for building intelligent computer systems.",
  "prereq_prose": "Prerequisites: COMS W3134 or COMS W3136 or COMS W3137.",
  "prereq_expr": {"any": [{"course": "COMS W3134"}, {"course": "COMS W3136"}, {"course": "COMS W3137"}]},
  "prereq_confidence": "parsed",
  "bulletin_url": "https://bulletin.columbia.edu/columbia-college/departments-instruction/computer-science/",
  "department_code": "COMS"
}
```
