# institution

Canonical module: `backend/src/starmap/contracts/institution.py`.

One institution in the California community college to UC/CSU corridor, as ASSIST publishes it.
The rows are the sending and receiving endpoints every `Agreement` points at, and the source of the institution pickers in Mode A.

Field values are transcribed from the captured `backend/tests/fixtures/assist/institutions.json` (181 institutions; 116 with `isCommunityCollege: true`).
This contract holds the NORMALIZED row: `assist/normalize.py` (increment 5) does the stripping and the `kind` derivation, so nothing here re-implements payload cleanup.

## Fields

| Field | Type | Constraints |
| --- | --- | --- |
| `assist_id` | int | `gt=0`; the ASSIST institution id (`id` in the payload) is the sole identifier. |
| `code` | str | 1..8 chars, pattern `^[A-Z][A-Z0-9]{0,7}$`. |
| `name` | str | 1..200 chars; control-character hygiene. |
| `kind` | `Literal["cc", "uc", "csu"]` | Which side of the corridor this institution sits on. |

`assist_id` is the sole id, a locked deviation from the plan's two-column `institutions(id, assist_id, ...)` sketch: a second internal id would be unused generality when the ASSIST id is already stable, unique, and the only join key every other contract and every fetch URL uses.

`code` arrives space-padded in the payload (`"UCSD    "`, `"DAC     "`), so the trailing-space strip happens in `assist/normalize.py`, not here.
A contract that accepted padded codes would let the same institution exist under two spellings.

`kind` is derived normalize-side from `isCommunityCollege` and `category`: category 2 (`isCommunityCollege: true`) is `cc`, category 1 is `uc`, category 0 is `csu`.
Category 5 (private/independent) institutions are out of corridor scope and never reach this contract; the normalizer drops them.

## Validators

No model validators.
Every rule above is a field constraint.

| Validator | Rule |
| --- | --- |
| `name` control-char check | Rejects codepoints below 0x20 other than `\n\r\t`, naming the offending `U+XXXX`. |

## Fixtures

Valid, transcribed from `institutions.json`:

| Fixture | Source row |
| --- | --- |
| `de_anza.json` | id 113, `"DAC     "` -> `DAC`, De Anza College, `cc` (category 2). |
| `ucsd.json` | id 7, `"UCSD    "` -> `UCSD`, University of California, San Diego, `uc` (category 1). |
| `sjsu.json` | id 39, `"SJSU    "` -> `SJSU`, San Jose State University, `csu` (category 0). |

Invalid: `assist_id_zero`, `bad_code_pattern`, `name_empty`, `name_control_char`, `bad_kind`.
`name_control_char` is not in doc 01's locked list; it is added because the hygiene validator would otherwise be the one rule with no fixture proving it fires, which the increment's exit criteria forbid.
