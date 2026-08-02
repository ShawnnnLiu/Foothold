# llm_call_log

Canonical module: `backend/src/starmap/contracts/llm_call_log.py`.

One frozen record per provider call, per tech reference 4.2 with the Foothold deltas: `plan_version` is dropped entirely (only `run_id` is logged).
The record stores identifiers, counts, hashes, and outcome metadata ONLY, never raw prompts or responses; `extra="forbid"` makes a raw-content field structurally impossible.
Every provider call appends exactly one row, including a call that failed in transport (logged with zero tokens).

## LlmNode

The closed enum of callers allowed to write to this log.
Foothold has exactly two LLM nodes, both request-time; no other caller may log here.

| Value | Meaning |
| --- | --- |
| `transcript_parser` | The request-time transcript parser (messy human input in). |
| `petition_writer` | The request-time petition writer (grounded human output out). |

## Fields

| Field | Type | Constraints |
| --- | --- | --- |
| `llm_call_log_id` | str | Pattern `^llm_call_[0-9a-f]{16}$`; minted by the injected `IdGenerator`. |
| `run_id` | str | Non-empty; preserved across layers. |
| `node` | enum | One of the `LlmNode` values above. |
| `prompt_version` | str | Non-empty; the hand-maintained label pinned by the prompt-pin tests. |
| `model_name` | str | Non-empty. |
| `attempt` | int | 0..2; the repair attempt index (at most 2 repairs, so at most 3 attempts). |
| `sdk_retry` | int | 0..2; the retry index inside one attempt (at most 2 retries, so at most 3 provider calls). |
| `input_tokens` | int | >= 0. |
| `output_tokens` | int | >= 0. |
| `cache_creation_tokens` | int | >= 0; priced at 1.25x the base input rate. |
| `cache_read_tokens` | int | >= 0; priced at 0.10x the base input rate. |
| `cost_estimate_usd` | float | >= 0; an estimate, never a billing fact. |
| `latency_ms` | int | >= 0; measured across the transport call via the injected clock. |
| `validation_outcome` | literal | One of `pass`, `fail`. |
| `reason_code` | `LlmReasonCode` or null | Non-null if and only if the outcome is `fail`. |
| `cache_hit` | bool | Must equal `cache_read_tokens > 0`. |
| `truncated` | bool | Deliberately unconstrained: a truncation that still parsed and validated stays `pass`; the flag preserves the provider's stop reason. |
| `refusal` | bool | A refusal implies `fail`. |
| `prompt_hash` | str or null | Pattern `^[0-9a-f]{64}$`; sha256 over the FULL rendered bytes (`system + "\n" + user_prompt + (repair_suffix or "")`). |
| `response_hash` | str or null | Pattern `^[0-9a-f]{64}$`; sha256 over the raw response text. Null when transport failed before a response arrived. |
| `created_at` | datetime | Timezone-aware. |

## Validators

| Validator | Rule |
| --- | --- |
| Reason code iff fail | `reason_code is not None` exactly when `validation_outcome == "fail"`; the message names the field and quotes both values. Fires in both directions. |
| Refusal implies fail | `refusal` true requires `validation_outcome == "fail"`. |
| Cache hit derivation | `cache_hit == (cache_read_tokens > 0)`; the message quotes both values. |
| Timezone-aware timestamp | `created_at.tzinfo` is set and resolves an offset. |

## Store

`SqliteCallLogStore` in `backend/src/starmap/llm/call_log.py`, append-only.

- Component `llm_call_log`, schema version 1.
- DDL: `llm_call_logs(llm_call_log_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL)` plus an index on `run_id`.
- `payload` is the canonical model JSON; reads re-validate through this contract.
- A duplicate `llm_call_log_id` raises the typed `CallLogAlreadyExistsError`, enforced by an explicit `SELECT` inside the insert transaction, never by catching a primary-key violation.
- `list_for_run` and `list_all` return rows in insertion order.

## Example

```json
{
  "llm_call_log_id": "llm_call_0000000000000001",
  "run_id": "run_demo",
  "node": "transcript_parser",
  "prompt_version": "transcript-parser-v1",
  "model_name": "claude-sonnet-5",
  "attempt": 0,
  "sdk_retry": 0,
  "input_tokens": 1200,
  "output_tokens": 340,
  "cache_creation_tokens": 0,
  "cache_read_tokens": 800,
  "cost_estimate_usd": 0.008706,
  "latency_ms": 1450,
  "validation_outcome": "pass",
  "reason_code": null,
  "cache_hit": true,
  "truncated": false,
  "refusal": false,
  "prompt_hash": "9f2c1f2ba3f6c0d21f5f1d5b6f6f2f0f5a1c9e8d7b6a5f4e3d2c1b0a9f8e7d6c",
  "response_hash": "1a2b3c4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f708192a3b4c5d6e7f809",
  "created_at": "2026-07-31T12:00:00Z"
}
```
