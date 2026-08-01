# reason_codes

Canonical module: `backend/src/starmap/contracts/reason_codes.py`.

Typed reason-code families as `StrEnum`s.
Values are snake_case and the families are append-only forever: a member is never renamed or removed.
Adding a member updates this spec in the same commit.
Week 2 adds the pathway violation family to this module.

## LlmReasonCode

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

## PrereqExtractionCode

| Value | Meaning |
| --- | --- |
| `unknown_course_leaf` | A proposed course leaf is outside the linked/catalog code set. |
| `unaccounted_linked_code` | A hyperlinked code is in neither the tree nor a note. |
| `expr_too_deep` | The proposed expression nests deeper than 3 levels. |

## BuildCode

| Value | Meaning |
| --- | --- |
| `dept_fetch_failed` | A department page could not be fetched. |
| `dept_parse_failed` | A department page could not be parsed. |
| `dept_excluded` | The department was excluded from the build after a failure. |

## CorpusCode

| Value | Meaning |
| --- | --- |
| `content_hash_mismatch` | Stored or supplied text does not hash to the recorded `content_hash`. |
| `document_conflict` | A re-register attempt carried a different document for an existing `doc_id`. |
| `unknown_document` | A referenced `doc_id` is not in the registry. |
| `empty_snapshot` | A snapshot was requested over zero documents. |
| `fts5_unavailable` | The SQLite build lacks the FTS5 extension. |
| `snapshot_not_indexed` | Retrieval was attempted against a snapshot with no built index. |

## Example

```python
from starmap.contracts.reason_codes import LlmReasonCode

LlmReasonCode.REPAIR_LIMIT_EXCEEDED.value == "repair_limit_exceeded"
```
