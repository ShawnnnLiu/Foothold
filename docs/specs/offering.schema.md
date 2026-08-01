# offering

Canonical module: `backend/src/starmap/contracts/offering.py`.

One term offering of a course, parsed from the bulletin's `desc_sched` blocks.

## Fields

| Field | Type | Constraints |
| --- | --- | --- |
| `course_code` | str | Normalized via `normalize_course_code`; must match `COURSE_CODE_RE`. |
| `term` | literal | One of `fall`, `spring`, `summer`. |
| `year` | int | 2020..2035. |
| `instructors` | list[str] | Each 1..100 chars; case-insensitively unique via `find_duplicates`; may be empty. |

## Validators

| Validator | Rule |
| --- | --- |
| `instructors` uniqueness | `find_duplicates` over the list must be empty; the message quotes the first-seen spellings of the duplicates. |

## Example

```json
{
  "course_code": "COMS W1002",
  "term": "fall",
  "year": 2026,
  "instructors": ["Ada Lovelace", "Grace Hopper"]
}
```
