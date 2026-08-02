"""The LLM generation engine (tech reference 4.1, with the Foothold deltas).

Two nested loops:

- the OUTER loop is bounded repair: at most `max_repair_attempts` repairs, so at
  most three attempts. Violation feedback never gets concatenated onto the user
  prompt; it travels as a SEPARATE `repair_suffix` through a distinct transport
  kwarg, so `user_prompt` stays byte-identical on every attempt and the provider
  can serve the base prompt from cache.
- the INNER loop is provider retries: at most `max_sdk_retries` retries, so at
  most three provider calls per attempt. Every provider call appends exactly one
  call-log row. Budgets compose: 3 x 3 = 9 calls worst case, 9 rows.

Boundary revalidation is deliberate: the transport asks the provider for
schema-shaped output, but the engine still validates the raw payload through
`output_contract`, because a payload can satisfy the wire schema and still
violate cross-field contract invariants.
"""

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from starmap.common.clock import Clock
from starmap.common.ids import IdGenerator, sha256_hex
from starmap.contracts.llm_call_log import LlmCallLogRecord, LlmNode
from starmap.contracts.reason_codes import LlmReasonCode
from starmap.llm.call_log import CallLogStore
from starmap.llm.errors import GenerationError, TransportError

REPAIR_PREAMBLE = (
    "\n\nYour previous output was rejected by deterministic validation. "
    "Fix exactly these problems and return the corrected object:\n"
)

REPAIR_LINE = "- field: {path} | constraint: {constraint} | offending value: {value}"
CLIP_LIMIT = 120
CLIP_MARKER = "...[clipped]"

ID_PREFIX = "llm_call"
REFUSAL_STOP_REASON = "refusal"
TRUNCATED_STOP_REASON = "max_tokens"


@dataclass(frozen=True, slots=True)
class TransportResult:
    """One provider response, normalized.

    `payload` is null when the response text could not be parsed into an
    object. `raw_text` is hashed for the log and surfaced only through the
    debug sink; it never reaches a log field.
    """

    payload: dict[str, Any] | None
    raw_text: str
    stop_reason: str
    input_tokens: int
    output_tokens: int
    cache_creation_tokens: int = 0
    cache_read_tokens: int = 0


class Transport(Protocol):
    """The seam tests replace with `FakeTransport`."""

    def complete(
        self,
        *,
        model_name: str,
        max_tokens: int,
        system: str,
        user_prompt: str,
        output_contract: type[BaseModel],
        repair_suffix: str | None = None,
        timeout_seconds: float = 300.0,
    ) -> TransportResult: ...


class AdapterConfig(BaseModel):
    """Engine-internal configuration.

    Defined here rather than in `contracts/` because it is engine config, not a
    wire contract. The retry and repair caps live in the FIELD CONSTRAINTS, so a
    config that exceeds a bound fails validation instead of being clamped.
    """

    # `contracts.base.FROZEN` plus `protected_namespaces=()` for `model_name`.
    model_config = ConfigDict(extra="forbid", frozen=True, protected_namespaces=())

    model_name: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    max_tokens: int = Field(gt=0)
    input_price_per_mtok: float = Field(ge=0)
    output_price_per_mtok: float = Field(ge=0)
    max_sdk_retries: int = Field(default=2, ge=0, le=2)
    max_repair_attempts: int = Field(default=2, ge=0, le=2)
    timeout_seconds: float = Field(default=300.0, gt=0)
    retry_backoff_seconds: float = Field(default=1.0, ge=0)


def clip(value: object) -> str:
    """Stringify and clip at `CLIP_LIMIT` with an explicit marker.

    Model-level validators receive the whole object; clipping keeps the
    re-prompt guidance without echoing a second copy of the rejected output.
    """
    text = value if isinstance(value, str) else repr(value)
    if len(text) <= CLIP_LIMIT:
        return text
    return text[:CLIP_LIMIT] + CLIP_MARKER


def format_validation_error(error: ValidationError) -> str:
    """Render pydantic violations through the one repair-line renderer."""
    lines = []
    for detail in error.errors():
        path = ".".join(str(part) for part in detail["loc"]) or "(root)"
        constraint = f"{detail['type']}: {detail['msg']}"
        lines.append(
            REPAIR_LINE.format(path=path, constraint=constraint, value=clip(detail.get("input")))
        )
    return "\n".join(lines)


def format_post_validate_error(error: ValueError, model: BaseModel) -> str:
    """Render a post-validator rejection through the same renderer."""
    return REPAIR_LINE.format(
        path="(root)",
        constraint=f"post_validate: {error}",
        value=clip(model.model_dump()),
    )


def format_malformed_output(output_contract: type[BaseModel], raw_text: str) -> str:
    """Render an unparseable response, listing the contract's required top-level keys."""
    required = [name for name, field in output_contract.model_fields.items() if field.is_required()]
    constraint = (
        "malformed_output: the response was not a JSON object; return a JSON object "
        f"with these required top-level keys: {', '.join(required)}"
    )
    return REPAIR_LINE.format(path="(root)", constraint=constraint, value=clip(raw_text))


def estimate_cost_usd(
    *,
    input_tokens: int,
    output_tokens: int,
    cache_creation_tokens: int,
    cache_read_tokens: int,
    input_price_per_mtok: float,
    output_price_per_mtok: float,
) -> float:
    """Cache writes bill at 1.25x and cache reads at 0.10x the base input rate.

    An estimate, not a billing fact.
    """
    billed_input = input_tokens + 1.25 * cache_creation_tokens + 0.10 * cache_read_tokens
    return (billed_input * input_price_per_mtok + output_tokens * output_price_per_mtok) / 1e6


class GenerationEngine[T: BaseModel]:
    """One engine per LLM node."""

    def __init__(
        self,
        node_name: str,
        output_contract: type[T],
        config: AdapterConfig,
        transport: Transport,
        call_log_store: CallLogStore,
        clock: Clock,
        id_generator: IdGenerator,
        debug_raw_sink: Callable[[str], None] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        attempt_recorder: Callable[[LlmCallLogRecord], None] | None = None,
    ) -> None:
        self.node = LlmNode(node_name)
        self.output_contract = output_contract
        self.config = config
        self.transport = transport
        self.call_log_store = call_log_store
        self.clock = clock
        self.id_generator = id_generator
        self.debug_raw_sink = debug_raw_sink
        self.sleeper = sleeper
        self.attempt_recorder = attempt_recorder

    def generate(
        self,
        *,
        run_id: str,
        system: str,
        user_prompt: str,
        post_validate: Callable[[T], None] | None = None,
    ) -> T:
        """Run the bounded repair loop and return a validated model."""
        repair_context: str | None = None
        for attempt in range(self.config.max_repair_attempts + 1):
            repair_suffix = None if repair_context is None else REPAIR_PREAMBLE + repair_context
            outcome = self._run_attempt(
                run_id=run_id,
                attempt=attempt,
                system=system,
                user_prompt=user_prompt,
                repair_suffix=repair_suffix,
                post_validate=post_validate,
            )
            if not isinstance(outcome, str):
                return outcome
            repair_context = outcome
        raise GenerationError(
            f"{self.node.value} failed validation after "
            f"{self.config.max_repair_attempts} repair attempts",
            reason_code=LlmReasonCode.REPAIR_LIMIT_EXCEEDED,
        )

    def _run_attempt(
        self,
        *,
        run_id: str,
        attempt: int,
        system: str,
        user_prompt: str,
        repair_suffix: str | None,
        post_validate: Callable[[T], None] | None,
    ) -> T | str:
        """One repair attempt: up to `max_sdk_retries + 1` provider calls.

        Returns the validated model on success, or repair text the outer loop
        feeds back as the next attempt's suffix.
        """
        prompt_hash = sha256_hex(system + "\n" + user_prompt + (repair_suffix or ""))
        for sdk_retry in range(self.config.max_sdk_retries + 1):
            is_last_retry = sdk_retry == self.config.max_sdk_retries
            started = self.clock.monotonic()
            try:
                result = self.transport.complete(
                    model_name=self.config.model_name,
                    max_tokens=self.config.max_tokens,
                    system=system,
                    user_prompt=user_prompt,
                    output_contract=self.output_contract,
                    repair_suffix=repair_suffix,
                    timeout_seconds=self.config.timeout_seconds,
                )
            except TransportError as error:
                latency_ms = self._latency_ms(started)
                code = error.llm_reason_code or LlmReasonCode.CALL_FAILED
                if not error.retryable:
                    self._log_transport_failure(
                        run_id=run_id,
                        attempt=attempt,
                        sdk_retry=sdk_retry,
                        reason_code=code,
                        latency_ms=latency_ms,
                        prompt_hash=prompt_hash,
                    )
                    raise GenerationError(
                        f"{self.node.value} transport failed permanently: {error.message}",
                        reason_code=code,
                    ) from error
                if is_last_retry:
                    self._log_transport_failure(
                        run_id=run_id,
                        attempt=attempt,
                        sdk_retry=sdk_retry,
                        reason_code=LlmReasonCode.RETRY_LIMIT_EXCEEDED,
                        latency_ms=latency_ms,
                        prompt_hash=prompt_hash,
                    )
                    raise GenerationError(
                        f"{self.node.value} exhausted {self.config.max_sdk_retries} retries: "
                        f"{error.message}",
                        reason_code=LlmReasonCode.RETRY_LIMIT_EXCEEDED,
                    ) from error
                self._log_transport_failure(
                    run_id=run_id,
                    attempt=attempt,
                    sdk_retry=sdk_retry,
                    reason_code=code,
                    latency_ms=latency_ms,
                    prompt_hash=prompt_hash,
                )
                self.sleeper(self.config.retry_backoff_seconds * (2**sdk_retry))
                continue

            latency_ms = self._latency_ms(started)
            if self.debug_raw_sink is not None:
                self.debug_raw_sink(result.raw_text)
            truncated = result.stop_reason == TRUNCATED_STOP_REASON
            log = self._row_builder(
                run_id=run_id,
                attempt=attempt,
                sdk_retry=sdk_retry,
                result=result,
                latency_ms=latency_ms,
                truncated=truncated,
                prompt_hash=prompt_hash,
            )

            if result.stop_reason == REFUSAL_STOP_REASON:
                # A refusal is never retried: same input, same answer.
                self._append(log(outcome="fail", reason_code=LlmReasonCode.REFUSAL, refusal=True))
                raise GenerationError(
                    f"{self.node.value} was refused by the provider",
                    reason_code=LlmReasonCode.REFUSAL,
                )

            if result.payload is None:
                if truncated:
                    if is_last_retry:
                        self._append(
                            log(outcome="fail", reason_code=LlmReasonCode.RETRY_LIMIT_EXCEEDED)
                        )
                        raise GenerationError(
                            f"{self.node.value} output stayed truncated across "
                            f"{self.config.max_sdk_retries} retries",
                            reason_code=LlmReasonCode.RETRY_LIMIT_EXCEEDED,
                        )
                    self._append(log(outcome="fail", reason_code=LlmReasonCode.TRUNCATED))
                    continue
                self._append(log(outcome="fail", reason_code=LlmReasonCode.MALFORMED_OUTPUT))
                return format_malformed_output(self.output_contract, result.raw_text)

            try:
                model = self.output_contract.model_validate(result.payload)
            except ValidationError as error:
                self._append(log(outcome="fail", reason_code=LlmReasonCode.SCHEMA_REJECTED))
                return format_validation_error(error)

            if post_validate is not None:
                try:
                    post_validate(model)
                except ValueError as error:
                    self._append(log(outcome="fail", reason_code=LlmReasonCode.SCHEMA_REJECTED))
                    return format_post_validate_error(error, model)

            self._append(log(outcome="pass"))
            return model

        raise AssertionError("unreachable: the retry loop always returns or raises")

    def _latency_ms(self, started: float) -> int:
        return max(0, round((self.clock.monotonic() - started) * 1000))

    def _row_builder(
        self,
        *,
        run_id: str,
        attempt: int,
        sdk_retry: int,
        result: TransportResult,
        latency_ms: int,
        truncated: bool,
        prompt_hash: str,
    ) -> Callable[..., LlmCallLogRecord]:
        def build(
            *,
            outcome: Literal["pass", "fail"],
            reason_code: LlmReasonCode | None = None,
            refusal: bool = False,
        ) -> LlmCallLogRecord:
            return LlmCallLogRecord(
                llm_call_log_id=self.id_generator.new_id(ID_PREFIX),
                run_id=run_id,
                node=self.node,
                prompt_version=self.config.prompt_version,
                model_name=self.config.model_name,
                attempt=attempt,
                sdk_retry=sdk_retry,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                cache_creation_tokens=result.cache_creation_tokens,
                cache_read_tokens=result.cache_read_tokens,
                cost_estimate_usd=estimate_cost_usd(
                    input_tokens=result.input_tokens,
                    output_tokens=result.output_tokens,
                    cache_creation_tokens=result.cache_creation_tokens,
                    cache_read_tokens=result.cache_read_tokens,
                    input_price_per_mtok=self.config.input_price_per_mtok,
                    output_price_per_mtok=self.config.output_price_per_mtok,
                ),
                latency_ms=latency_ms,
                validation_outcome=outcome,
                reason_code=reason_code,
                cache_hit=result.cache_read_tokens > 0,
                truncated=truncated,
                refusal=refusal,
                prompt_hash=prompt_hash,
                response_hash=sha256_hex(result.raw_text),
                created_at=self.clock.now(),
            )

        return build

    def _log_transport_failure(
        self,
        *,
        run_id: str,
        attempt: int,
        sdk_retry: int,
        reason_code: LlmReasonCode,
        latency_ms: int,
        prompt_hash: str,
    ) -> None:
        """A transport failure still logs a row, with zero tokens and no response hash."""
        self._append(
            LlmCallLogRecord(
                llm_call_log_id=self.id_generator.new_id(ID_PREFIX),
                run_id=run_id,
                node=self.node,
                prompt_version=self.config.prompt_version,
                model_name=self.config.model_name,
                attempt=attempt,
                sdk_retry=sdk_retry,
                input_tokens=0,
                output_tokens=0,
                cache_creation_tokens=0,
                cache_read_tokens=0,
                cost_estimate_usd=0.0,
                latency_ms=latency_ms,
                validation_outcome="fail",
                reason_code=reason_code,
                cache_hit=False,
                truncated=False,
                refusal=False,
                prompt_hash=prompt_hash,
                response_hash=None,
                created_at=self.clock.now(),
            )
        )

    def _append(self, record: LlmCallLogRecord) -> None:
        self.call_log_store.append(record)
        if self.attempt_recorder is not None:
            self.attempt_recorder(record)
