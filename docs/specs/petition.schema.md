# petition

Canonical module: `backend/src/starmap/contracts/petition.py`.

The petition artifact: the stored and polled result of the petition-writer node, plus the node's LLM output contract.

Three models.
`PetitionDraft` is what the LLM must return: one key, the letter.
`Petition` is what the web seam stores at job creation, updates when the node finishes, and serves to the polling client.
`CitedCourse` is the deterministic per-course citation index the UI renders beside the letter.

Everything except `PetitionDraft.letter_text` on the success path is computed deterministically.
The letter itself is LLM output that has already survived schema validation and the citation validator (`llm/petition_writer.py`), or it is the deterministic template letter on the fallback path.
The vocabulary gate, second half, binds here: the findings bundle handed to the petition prompt IS the object the citation validator checks the letter against, so a letter may only cite what a selected finding already carries.

## PetitionDraft (the LLM output contract)

| Field | Type | Constraints |
| --- | --- | --- |
| `letter_text` | str | 200..8000 chars; control-character hygiene (`\n`, `\r`, `\t` admitted). |

One key on purpose: the letter is the whole proposal, and every other wire field is computed deterministically.
The 200-char floor rejects degenerate output cheaply at the schema gate, where it produces a repairable violation.

## CitedCourse

| Field | Type | Constraints |
| --- | --- | --- |
| `course_code` | str | Normalized via `normalize_course_code`; values come from `Finding.student_course_codes`, which are already normalized. |
| `finding_position` | int | `ge=0`; an index into the evaluation's findings list. |

## Petition (the stored and polled artifact)

| Field | Type | Constraints |
| --- | --- | --- |
| `petition_id` | str | Pattern `^pet_[0-9a-f]{16}$`; minted via `IdGenerator.new_id("pet")`. |
| `evaluation_id` | str | Pattern `^eval_[0-9a-f]{16}$`, shared with `Evaluation.evaluation_id`. |
| `finding_positions` | list[int] | Min length 1; each `ge=0`; strictly ascending (which enforces uniqueness). |
| `status` | `Literal["pending", "succeeded", "failed"]` | |
| `reason_code` | LlmReasonCode \| None | Default `None`. |
| `fallback` | bool | Default `False`. |
| `letter_text` | str \| None | Default `None`; when present, the `PetitionDraft` constraints (200..8000, hygiene). |
| `cited` | list[CitedCourse] | Default empty. |
| `created_at` | datetime | Timezone-aware. |

The `fallback` flag lives only on `succeeded` by construction: a fallback letter is a success with a recorded reason the LLM draft was discarded.
`repair_limit_exceeded` is the one reason code that takes the fallback path; every other `GenerationError` fails the petition outright with its typed reason code (`docs/implementation-plans/llm-nodes/00-overview.md`, decision 4).

### Petition validators

| Validator | Rule |
| --- | --- |
| positions ascending | `finding_positions` strictly ascending; the error quotes the list. |
| pending shape | `status == "pending"` requires `letter_text` null, `cited` empty, `fallback` false, `reason_code` null. |
| succeeded shape | `status == "succeeded"` requires `letter_text` non-null, and `reason_code` non-null IFF `fallback` is true (both directions). |
| failed shape | `status == "failed"` requires `letter_text` null, `cited` empty, `fallback` false, `reason_code` non-null. |
| cited positions selected | Every `cited[].finding_position` is a member of `finding_positions`. |
| created_at tz-aware | Naive datetimes rejected, quoting the ISO value. |

## Fixtures

Valid:

| Fixture | What it pins |
| --- | --- |
| `pending.json` | The row the POST route inserts before the background task runs. |
| `succeeded.json` | An LLM letter with its `cited` index; `fallback` false, `reason_code` null. |
| `succeeded_fallback.json` | The template-letter path: `fallback` true with `reason_code` `repair_limit_exceeded`. |
| `failed.json` | A typed failure: `reason_code` present, letter null, `cited` empty. |
| `draft_minimal.json` | The smallest legal `PetitionDraft`: one letter at the 200-char floor. |

`draft_*` fixtures validate against `PetitionDraft`; every other fixture validates against `Petition`.

Invalid: `bad_petition_id`, `bad_evaluation_id`, `empty_positions`, `negative_position`, `unsorted_positions`, `duplicate_positions`, `pending_with_letter`, `pending_with_reason_code`, `pending_with_fallback`, `succeeded_without_letter`, `succeeded_reason_without_fallback`, `succeeded_fallback_without_reason`, `failed_without_reason`, `failed_with_letter`, `cited_position_not_selected`, `cited_bad_course_code`, `letter_too_short`, `letter_too_long`, `letter_control_char`, `naive_created_at`, `draft_missing_letter`, `draft_extra_key`.
Each invalid fixture carries its `.expected.json` sidecar per the harness pattern in `backend/tests/fixtures/invalid/llm_call_log/`.
