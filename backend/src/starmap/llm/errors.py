"""Typed errors for the LLM region (tech reference 4.1).

Two error classes, and one rule about a third:

- `TransportError` is raised by a transport when the provider call fails.
  `retryable` discriminates transient provider weather (rate limit, overload,
  connection blip, timeout) from permanent rejections (bad credentials,
  malformed request), where retrying is pure noise. Messages carry the SDK
  exception TYPE NAME only, never bodies: bodies may quote request content or
  credentials.
- `GenerationError` is the engine's terminal error and always carries an
  `LlmReasonCode`.
- Post-validators raise plain `ValueError` (repairable) and must NEVER raise
  `GenerationError`; the engine lets a `GenerationError` from a post-validator
  propagate untouched, which makes that a loud programming error rather than a
  silently-consumed one.
"""

from starmap.common.errors import StarmapError
from starmap.contracts.reason_codes import LlmReasonCode


class TransportError(StarmapError):
    """A provider call failed inside a transport."""

    def __init__(
        self,
        message: str,
        *,
        retryable: bool = True,
        reason_code: LlmReasonCode | None = None,
    ) -> None:
        super().__init__(message, reason_code=reason_code)
        self.retryable = retryable
        self.llm_reason_code = reason_code


class GenerationError(StarmapError):
    """Terminal engine failure; always carries a typed reason code."""

    def __init__(self, message: str, *, reason_code: LlmReasonCode) -> None:
        super().__init__(message, reason_code=reason_code)
        self.llm_reason_code = reason_code
