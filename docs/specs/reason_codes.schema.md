# reason_codes

Canonical module: `backend/src/starmap/contracts/reason_codes.py`.

Typed reason-code families as `StrEnum`s.
Values are snake_case and the families are append-only forever: a member is never renamed or removed.
Adding a member updates this spec in the same commit.

## The one-time pivot exception (2026-07-31)

The append-only-forever rule exists so that a persisted or logged code can never dangle.
On 2026-07-31 the product pivoted from the Columbia course-selection helper to Astrolabe, and three families were removed: `PrereqExtractionCode`, `BuildCode`, and `CorpusCode`.
The rule was not violated, because its premise never held for them: none of the three ever shipped a producer, no artifact or log row anywhere carries their values, and the consumers that would have emitted them (bulletin fetch/parse, prereq extraction, the document-registry corpus stack) were retired by the pivot before they were ever built.
`LlmReasonCode` was untouched: its consumer, the LLM backbone, is alive.
This is a recorded one-time exception under the pivot approval, not a precedent; append-only binds normally from here.

## LlmReasonCode

Producer: `llm/engine.py`, `llm/transport_anthropic.py`, `llm/errors.py`.

| Value | Meaning |
| --- | --- |
| `auth_failed` | The LLM provider rejected our credentials. |
| `rate_limited` | The provider rate limit was hit and retries were exhausted. |
| `call_failed` | Transport or provider failure that is not auth or rate limiting. |
| `retry_limit_exceeded` | Retryable failures persisted past the retry budget. |
| `refusal` | The model refused to produce output. |
| `truncated` | The model output was cut off before completion. |
| `malformed_output` | The model output could not be parsed into the expected structure. |
| `schema_rejected` | Parsed output failed contract validation. |
| `repair_limit_exceeded` | Validation kept failing after the bounded repair attempts (max 2). |

## EvaluationFindingCode

Producer: `transfer/evaluate.py` (implementation plan doc 03).
Every finding the deterministic evaluator emits carries exactly one of these.

| Value | Meaning |
| --- | --- |
| `transfers_clean` | The student's courses satisfy the articulation outright, with no advisement attached. |
| `advisement_note` | The articulation is satisfied but carries an ASSIST advisement (a `note` leaf), which is never silently satisfied. |
| `partial_series` | Some but not all courses of a required series or `all` group are present. |
| `fuzzy_match` | A student course resolved to the `cc_courses` vocabulary by similarity rather than exact code. |
| `stale_year` | The agreement consulted is not the latest published academic year for the pair. |
| `no_articulation` | The agreement publishes no articulation for the receiving course ("No Course Articulated"). |
| `still_owed` | A receiving requirement remains unsatisfied by the submitted course set. |
| `double_count_risk` | One student course is being used to satisfy more than one receiving requirement. |
| `unresolved` | A submitted course could not be resolved against the sending institution's `cc_courses` projection. |

## TriageBucket

Producer: `transfer/triage.py`; the four columns of the triage board.

| Value | Meaning |
| --- | --- |
| `transfers_clean` | Green: the credit transfers with nothing to act on. |
| `at_risk` | Amber: the credit needs attention, whether from the agreement's own hedges or from input quality. |
| `no_articulation` | Red: the agreement asserts no articulation exists. |
| `still_owed` | Requirements the student has not yet covered. |

## BUCKET_FOR_CODE

Normative: this table IS the mapping asserted by `backend/tests/contracts/test_reason_codes.py`, and `Finding.bucket` is validated against it, so a finding's bucket has exactly one source of truth.
The mapping is total: every `EvaluationFindingCode` has a bucket.

| EvaluationFindingCode | TriageBucket |
| --- | --- |
| `transfers_clean` | `transfers_clean` |
| `advisement_note` | `at_risk` |
| `partial_series` | `at_risk` |
| `fuzzy_match` | `at_risk` |
| `stale_year` | `at_risk` |
| `double_count_risk` | `at_risk` |
| `unresolved` | `at_risk` |
| `no_articulation` | `no_articulation` |
| `still_owed` | `still_owed` |

`unresolved` maps to `at_risk`, not `no_articulation`, deliberately.
Red claims a fact about the agreement ("no articulation exists" is ground truth we are asserting on ASSIST's authority).
An unresolved course is instead an input-quality problem the student can fix by correcting what they typed, which is exactly amber's "needs attention" semantics.
Putting it in red would attribute a student typo to the articulation agreement.

## AssistBuildCode

Producer: `assist/fetch.py` and `assist/normalize.py` (implementation plan doc 02); every value appears in the build report as a typed exclusion, never as a silent drop.

| Value | Meaning |
| --- | --- |
| `session_bootstrap_failed` | The ASSIST session handshake did not yield a usable session. |
| `agreement_fetch_failed` | An agreement payload could not be fetched after its retries. |
| `envelope_invalid` | The response envelope did not match the expected ASSIST shape. |
| `field_decode_failed` | A stringified/double-encoded payload field could not be decoded. |
| `articulation_type_unsupported` | An articulation entry carries a `type` outside the supported set. |
| `course_code_unparseable` | A payload course code failed `normalize_course_code`. |
| `mixed_group_conjunction` | A sending group mixes conjunctions in a way the expression mapping cannot express. |
| `advisement_shape_unknown` | A non-empty `attributes` list was found, whose real shape is still fixture-pending. |
| `template_shape_unsupported` | A `templateAssets` structure is outside the modeled asset shapes. |
| `institution_kind_unknown` | An institution's category/`isCommunityCollege` pair does not map to `cc`/`uc`/`csu`. |
| `course_projection_conflict` | Two payload rows project to the same `cc_courses` key with different content. |

## RetrievalCode

Producer: `retrieval/errors.py` (implementation plan doc 04).

| Value | Meaning |
| --- | --- |
| `fts5_unavailable` | The SQLite build lacks the FTS5 extension; the index fails fast rather than degrading. |
| `institution_not_indexed` | Search was attempted against an institution with no built index. |

## Example

```python
from starmap.contracts.reason_codes import LlmReasonCode

LlmReasonCode.REPAIR_LIMIT_EXCEEDED.value == "repair_limit_exceeded"
```
