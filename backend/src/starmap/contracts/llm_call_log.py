"""LLM call-log record contract and the closed node enum.

Canonical spec: docs/specs/llm_call_log.schema.md.
The record stores identifiers, counts, hashes, and outcome metadata only;
`extra="forbid"` is what makes a raw-prompt or raw-response field
structurally impossible.
"""

from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from starmap.contracts.reason_codes import LlmReasonCode

# Same guarantees as `contracts.base.FROZEN`, plus `protected_namespaces=()`
# because `model_name` collides with pydantic's reserved `model_` prefix.
FROZEN_WITH_MODEL_FIELDS = ConfigDict(
    extra="forbid",
    frozen=True,
    protected_namespaces=(),
)

HASH_PATTERN = r"^[0-9a-f]{64}$"


class LlmNode(StrEnum):
    """The closed set of callers allowed to write to the call log.

    Astrolabe has exactly two LLM nodes, both request-time.
    """

    TRANSCRIPT_PARSER = "transcript_parser"
    PETITION_WRITER = "petition_writer"


class LlmCallLogRecord(BaseModel):
    model_config = FROZEN_WITH_MODEL_FIELDS

    llm_call_log_id: str = Field(pattern=r"^llm_call_[0-9a-f]{16}$")
    run_id: str = Field(min_length=1)
    node: LlmNode
    prompt_version: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    attempt: int = Field(ge=0, le=2)
    sdk_retry: int = Field(ge=0, le=2)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cache_creation_tokens: int = Field(ge=0)
    cache_read_tokens: int = Field(ge=0)
    cost_estimate_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)
    validation_outcome: Literal["pass", "fail"]
    reason_code: LlmReasonCode | None = None
    cache_hit: bool
    truncated: bool
    refusal: bool
    prompt_hash: str | None = Field(default=None, pattern=HASH_PATTERN)
    response_hash: str | None = Field(default=None, pattern=HASH_PATTERN)
    created_at: datetime

    @model_validator(mode="after")
    def _check_reason_code_iff_fail(self) -> "LlmCallLogRecord":
        failed = self.validation_outcome == "fail"
        if failed and self.reason_code is None:
            raise ValueError(
                "reason_code is required when validation_outcome is 'fail', but it is null"
            )
        if not failed and self.reason_code is not None:
            raise ValueError(
                f"reason_code must be null when validation_outcome is "
                f"{self.validation_outcome!r}, but it is {self.reason_code.value!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_refusal_implies_fail(self) -> "LlmCallLogRecord":
        if self.refusal and self.validation_outcome != "fail":
            raise ValueError(
                f"refusal is true, which requires validation_outcome 'fail', "
                f"but it is {self.validation_outcome!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_cache_hit_derivation(self) -> "LlmCallLogRecord":
        expected = self.cache_read_tokens > 0
        if self.cache_hit != expected:
            raise ValueError(
                f"cache_hit {self.cache_hit!r} does not match cache_read_tokens "
                f"{self.cache_read_tokens!r}; expected {expected!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_created_at_is_tz_aware(self) -> "LlmCallLogRecord":
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError(
                f"created_at must be timezone-aware, got naive value "
                f"{self.created_at.isoformat()!r}"
            )
        return self
