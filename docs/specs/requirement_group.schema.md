# requirement_group

Canonical module: `backend/src/starmap/contracts/requirement_group.py`.

One requirement group of a major: an `all` list, a `choose_n` list, or a prose `note` gate.

## Fields

| Field | Type | Constraints |
| --- | --- | --- |
| `requirement_group_id` | str | Pattern `^rg_[0-9a-f]{16}$`; must equal its derivation (below). |
| `major_id` | str | 1..64 chars, lowercase slug (`^[a-z0-9-]+$`). |
| `name` | str | 1..200 chars. |
| `rule_kind` | literal | One of `all`, `choose_n`, `note`. |
| `member_courses` | list[str] | Normalized course codes; case-insensitively unique; may be empty only for `note`. |
| `choose_n` | int or null | See kind-conditional rules; defaults to null. |
| `note_text` | str or null | 1..1000 chars when present; defaults to null. |

## Validators

| Validator | Rule |
| --- | --- |
| Id derivation | `requirement_group_id == "rg_" + sha256_hex(f"{major_id}\n{name}")[:16]`; the message quotes actual and derived ids. |
| `member_courses` uniqueness | `find_duplicates` over the codes must be empty. |
| Kind-conditional, `all` | Forbids `choose_n` and `note_text`; requires non-empty `member_courses`. |
| Kind-conditional, `choose_n` | Requires `choose_n` in 1..len(`member_courses`); forbids `note_text`. |
| Kind-conditional, `note` | Requires `note_text`; forbids `choose_n`. |

## Example

```json
{
  "requirement_group_id": "rg_c3d712ed3c9ec45b",
  "major_id": "computer-science",
  "name": "Electives",
  "rule_kind": "choose_n",
  "member_courses": ["COMS W4701", "COMS W4705", "COMS W4771"],
  "choose_n": 2,
  "note_text": null
}
```
