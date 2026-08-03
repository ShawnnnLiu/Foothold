# transcript_parse

Canonical module: `backend/src/starmap/contracts/transcript_parse.py`.

The transcript-parse artifact: the stored and polled result of the transcript-parser node, plus the node's LLM output contract.

Five models.
`ProposedCourse` and `TranscriptProposal` are what the LLM must return: the course entries it read in the pasted text, verbatim.
`TranscriptChip` is one resolved chip, the wire shape the UI consumes.
`UnresolvedEntry` is one verbatim read the vocabulary could not resolve, surfaced for manual fixing.
`TranscriptParse` is what the web seam stores at job creation, updates when the node finishes, and serves to the polling client.

The propose/dispose split binds here: the LLM proposes entries, the engine's bounded repair fixes schema and grounding violations only, and resolution against the `cc_courses` projection runs after the engine returns, deterministically, and never triggers repair.
A course the vocabulary does not contain is an `UnresolvedEntry` the student fixes by hand, not an LLM error: re-prompting cannot put a course into the catalog.
Chips take `course_code`, `title`, and units from the `cc_courses` row, never from the proposal, so a fabricated title cannot reach a chip.

## ProposedCourse (one LLM output row)

| Field | Type | Constraints |
| --- | --- | --- |
| `course_code` | str \| None | Default `None`; 1..32 chars; control-character hygiene. NOT normalized: the model copies the transcript verbatim, and `normalize_course_code` would force repair churn on shapes like `MATH20A` that resolution handles tolerantly. |
| `title` | str \| None | Default `None`; 1..300 chars; hygiene. |
| `units` | float \| None | Default `None`; `gt=0`, `le=20` (mirrors `StudentCourse.units`). |
| `term` | str \| None | Default `None`; 1..40 chars; hygiene. Captured because the plan names it; unused downstream in v1. |

Validator: at least one of `course_code` and `title` is non-null.
This is a repairable cross-field rule; the boundary-revalidation test uses it.

## TranscriptProposal (the LLM output contract)

| Field | Type | Constraints |
| --- | --- | --- |
| `courses` | list[ProposedCourse] | May be empty (a pasted page with no course lines is a valid read); max length `MAX_PROPOSED_COURSES = 60`, a module constant mirroring `routes.MAX_COURSES`. |

## TranscriptChip (one resolved chip, the wire shape doc 05 locks)

| Field | Type | Constraints |
| --- | --- | --- |
| `course_code` | `codes.CourseCode` | Normalized; comes from the `cc_courses` row, never from the proposal. |
| `title` | str | 1..300 chars; hygiene; the vocabulary row's title. |
| `units_min` | float | `gt=0`, `le=articulation.MAX_UNITS`. |
| `units_max` | float | `le=MAX_UNITS`; validator `units_max >= units_min` (mirrors `CcCourse`). |
| `resolution` | `Literal["exact", "fuzzy_match"]` | `unresolved` is structurally impossible here; that status becomes an `UnresolvedEntry`. |

## UnresolvedEntry

| Field | Type | Constraints |
| --- | --- | --- |
| `proposed_code` | str \| None | Default `None`; 1..32 chars; hygiene. |
| `proposed_title` | str \| None | Default `None`; 1..300 chars; hygiene. |

Validator: at least one field non-null.
These are the model's verbatim reads surfaced for manual fixing; they never become chips automatically (doc 05).

## TranscriptParse (the stored and polled artifact)

| Field | Type | Constraints |
| --- | --- | --- |
| `parse_id` | str | Pattern `^parse_[0-9a-f]{16}$`; minted via `IdGenerator.new_id("parse")`. |
| `sending_institution_id` | int | `gt=0`; the CC whose vocabulary resolved the chips (the doc-05 amendment in `docs/implementation-plans/llm-nodes/00-overview.md`). |
| `status` | `Literal["pending", "succeeded", "failed"]` | |
| `reason_code` | `LlmReasonCode \| None` | Default `None`. |
| `chips` | list[TranscriptChip] | Default empty. |
| `unresolved` | list[UnresolvedEntry] | Default empty. |
| `created_at` | datetime | Timezone-aware. |

A `succeeded` parse with both lists empty is legal: the model validly read a page containing no courses.

### TranscriptParse validators

| Validator | Rule |
| --- | --- |
| reason code iff failed | `reason_code` non-null IFF `status == "failed"` (both directions; same shape as the call-log rule). |
| non-succeeded emptiness | `status != "succeeded"` requires `chips` and `unresolved` both empty. |
| chip uniqueness | `find_duplicates` over `chips[].course_code`; the error names the duplicates. |
| created_at tz-aware | Naive datetimes rejected, quoting the ISO value. |

## Fixtures

Valid:

| Fixture | What it pins |
| --- | --- |
| `pending.json` | The row the POST route inserts before the background task runs. |
| `succeeded_mixed.json` | An exact chip, a fuzzy chip, and one unresolved entry together. |
| `succeeded_empty.json` | The legal empty success: a page with no course lines. |
| `failed.json` | A typed failure: `reason_code` present, both lists empty. |
| `proposal_minimal.json` | The smallest legal `TranscriptProposal`: one row carrying only a `course_code`. |

`proposal_*` fixtures validate against `TranscriptProposal`; every other fixture validates against `TranscriptParse`.

Invalid: `bad_parse_id`, `institution_id_zero`, `pending_with_chips`, `pending_with_reason_code`, `failed_without_reason`, `failed_with_unresolved`, `succeeded_with_reason`, `duplicate_chips`, `chip_bad_course_code`, `chip_units_zero`, `chip_units_max_below_min`, `chip_bad_resolution`, `unresolved_all_null`, `naive_created_at`, `proposal_row_all_null`, `proposal_too_many_courses`, `proposal_units_zero`, `proposal_title_control_char`, `proposal_extra_key`.
Each invalid fixture carries its `.expected.json` sidecar per the harness pattern in `backend/tests/fixtures/invalid/llm_call_log/`.
