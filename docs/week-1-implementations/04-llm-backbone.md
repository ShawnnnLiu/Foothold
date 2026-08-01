# Increment 4: LLM Backbone

Goal: the generation engine, call log, transports, and prompt-pinning scaffold, fully tested against FakeTransport with zero network.
Binding mechanism reference: TR 4.1 (engine), TR 4.2 (call log), TR 4.6 (FakeTransport, prompt pins), with the Starmap deltas from "Starmap deltas (kernels)".
Nothing in this increment makes a live API call.

## `llm/errors.py`

- `TransportError(StarmapError)` with `retryable: bool = True` and optional `reason_code`; message carries the SDK exception TYPE NAME only, never bodies (TR 4.1).
- `GenerationError(StarmapError)` terminal engine error, always carrying a `LlmReasonCode`.
- Post-validators raise plain `ValueError` (repairable) and must never raise `GenerationError`.

## `llm/engine.py`

Implement TR 4.1 exactly; restated here only where Starmap deviates or the table is load-bearing.

- Transport Protocol: `complete(*, model_name, max_tokens, system, user_prompt, output_contract, repair_suffix=None, timeout_seconds=300.0) -> TransportResult`.
- `TransportResult` frozen: `payload: dict | None`, `raw_text: str`, `stop_reason: str`, `input_tokens: int`, `output_tokens: int`, `cache_creation_tokens: int = 0`, `cache_read_tokens: int = 0`.
- `AdapterConfig`: a frozen pydantic model using `FROZEN`, defined in `llm/engine.py` rather than `contracts/` because it is engine-internal config, not a wire contract.
  Fields: `model_name`, `prompt_version`, `max_tokens`, `input_price_per_mtok`, `output_price_per_mtok`, `max_sdk_retries` (0..2, default 2), `max_repair_attempts` (0..2, default 2), `timeout_seconds` (default 300), `retry_backoff_seconds` (default 1.0).
  Caps live in field constraints, never clamped.
- Engine constructor: `(node_name, output_contract, config, transport, call_log_store, clock, id_generator, debug_raw_sink=None, sleeper=time.sleep, attempt_recorder=None)`.
  `node_name` is validated against the closed node enum (`prereq_extractor`, `pathway_proposer`).
- Outer loop `generate(*, run_id, system, user_prompt, post_validate=None)` per TR 4.1 (no `plan_version`: Starmap delta).
  Repair suffix wording exactly as TR 4.1's sketch; `user_prompt` byte-identical across attempts (cache stability), suffix travels as the separate kwarg.
- Inner loop outcome table, binding verbatim from TR 4.1:

| Outcome | Logged reason code | Behavior |
|---|---|---|
| transport error, non-retryable | its code or `call_failed` | log, raise typed immediately |
| transport error, retryable, not last | its code or `call_failed` | log, sleep `backoff * 2^retry`, continue |
| transport error, retryable, last | `retry_limit_exceeded` | log, raise typed |
| stop_reason refusal | `refusal` | log with refusal flag, raise typed, never retried |
| payload null + truncated, not last | `truncated` | log, continue |
| payload null + truncated, last | `retry_limit_exceeded` | log, raise typed |
| payload null, not truncated | `malformed_output` | log, return repair text listing the contract's required top-level keys |
| contract or post_validate rejects | `schema_rejected` | log, return formatted violation text |
| success | none | log pass, return validated model |

- Unified repair line format: `- field: {path} | constraint: {constraint} | offending value: {value}` with 120-char clip and explicit clip marker (TR 4.1).
- Cost estimate: `((input + 1.25*cache_write + 0.10*cache_read) * in_price + output * out_price) / 1e6`.
- `prompt_hash = sha256_hex(system + "\n" + user_prompt + (repair_suffix or ""))`; `response_hash = sha256_hex(raw_text)`.
- Boundary revalidation: the engine validates `payload` through `output_contract` even though the transport requested schema-shaped output (TR 4.1 corollary; a test constructs the passes-wire-schema-but-fails-cross-field case).

## `llm/call_log.py`

Per TR 4.2 minus `plan_version`.
Record contract `LlmCallLogRecord` (frozen, `extra="forbid"`, spec: `docs/specs/llm_call_log.schema.md`): `llm_call_log_id`, `run_id`, `node` (closed enum), `prompt_version`, `model_name`, `attempt`, `sdk_retry`, four token counters, `cost_estimate_usd`, `latency_ms`, `validation_outcome: Literal["pass", "fail"]`, `reason_code | None`, `cache_hit`, `truncated`, `refusal`, `prompt_hash | None`, `response_hash | None`, `created_at`.
Invariants as model validators: `reason_code` non-null iff fail; refusal implies fail; `cache_hit == (cache_read_tokens > 0)`; tz-aware `created_at`.
Store `SqliteCallLogStore(db)`: `append`, `list_for_run`, `list_all`; DDL `llm_call_logs(llm_call_log_id TEXT PRIMARY KEY, run_id TEXT NOT NULL, payload TEXT NOT NULL)` + run_id index; duplicate id is a typed already-exists error via explicit SELECT in the insert transaction; a transport failure still logs a row with zero tokens.
Add this contract to the schema registry and fixture inventory (invalid fixtures: reason-code-iff-fail both directions, refusal-without-fail, naive datetime).

## `llm/transport_anthropic.py`

The only SDK import site in the repo (with the SDK dependency approved in increment 0).

- Renders one user message with two content blocks: base prompt block carrying `cache_control: {"type": "ephemeral"}`, then the suffix block when present (TR 4.1 cache mechanism).
- Requests schema-shaped output via the provider's JSON-schema output format but returns the RAW parsed dict, never an SDK-validated object.
- Extended thinking explicitly disabled on every call; no sampling parameters.
- Error translation table (TR 4.1): auth/permission -> non-retryable `auth_failed`; rate limit -> retryable `rate_limited`; bad-request/not-found/unprocessable -> non-retryable `call_failed`; overloaded/5xx/connection/timeout -> retryable `call_failed`; message = exception type name only.
- Truncation: `stop_reason == "max_tokens"` maps to `truncated` semantics (payload may be None when JSON is cut mid-stream).
- Unit-test the translation and block assembly by monkeypatching the SDK client object; do not hit the network.
  If constructing real SDK exception instances is awkward, define the translation over `type(exc).__name__` membership sets so tests can use stand-in classes with matching names, and record that decision in the module docstring.

Model configs, locked: the prereq extractor config is `model_name="claude-sonnet-5"`, `prompt_version="prereq-extractor-v1"`, `max_tokens=2000`, prices set from the current public Anthropic pricing table at implementation time (verify via docs; record the values and date in a comment; they are estimate inputs, not billing facts).

## Test seams (`backend/tests/support/`)

- `FakeTransport` per TR 4.6: scripted list of `TransportResult | Exception`, records every call's kwargs, empty script asserts.
- Frozen clock and sequential id generator from increment 2.
- Recorded sleeper (appends durations).

## Prompt-pin scaffold

- Layer 1: `backend/tests/test_prompt_pins.py` with a table `(constant_name, pinned_version, pinned_sha256)`; hashes each system-prompt constant, asserts version and hash, prints the new hash on mismatch for copy-paste.
  Seed the table now with a placeholder entry structure and no rows; increment 5 adds the extractor row.
- Layer 2 harness: a builder helper that runs a node against a FakeTransport scripted so the FIRST response fails a deterministic check, capturing `(system, user_prompt, repair_suffix)` frames into a canonical text and sha256-pinning it, with rot-guard asserts for required and excluded blocks (TR 4.6).
  Implement the helper generically now; increment 5 instantiates it.

## Engine test list (the exit gate)

All against FakeTransport with frozen clock, sequential ids, recorded sleeper:

- Retry pacing: two retryable errors then success yields `sleeps == [1.0, 2.0]` and three log rows with correct `(attempt, sdk_retry)`.
- Non-retryable error: immediate typed raise, one log row, no sleep.
- Refusal: typed raise, refusal flag in the log, no retry.
- Truncation transient then success; truncation on last retry raises `retry_limit_exceeded`.
- Malformed payload: repair text lists the contract's required keys; second attempt carries `repair_suffix`; `requests[1].user_prompt == requests[0].user_prompt`.
- Schema rejection via cross-field validator on schema-valid payload (boundary revalidation pin).
- Repair cap exhaustion: `max_repair_attempts=2` yields exactly 3 attempts then `repair_limit_exceeded`.
- Worst case 9 provider calls, 9 log rows.
- Cost formula spot values including cache token classes; `cache_hit` flag.
- Log rows contain hashes only: assert no log field contains the prompt or response text.
- Post-validator raising `GenerationError` is a test-asserted programming error (engine converts or the test forbids it; lock: engine lets it propagate and a test documents that post-validators must raise `ValueError`).

## Exit criteria

- Full outcome table pinned by the tests above; `make check` green.
- Call log contract in the schema registry with fixtures.
- Anthropic transport merged but exercised only by unit tests; grep-gate test asserts `anthropic` is imported nowhere outside `llm/` (implement as a real test walking `src/starmap`).
