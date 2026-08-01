"""FakeTransport: the whole LLM testing seam (tech reference 4.6).

A script entry that is an `Exception` is RAISED (that is how transport failures
are scripted); a result with `stop_reason="refusal"` scripts a refusal; a result
with `payload=None` scripts malformed output. `requests` records every call's
kwargs and powers prompt-assembly assertions, the cache-stability pin, and the
full-prompt hash pins.
"""

import json
from collections.abc import Sequence
from typing import Any

from starmap.llm.engine import TransportResult

RAW_UNPARSEABLE = "RAW_UNPARSEABLE"


class FakeTransport:
    def __init__(self, script: Sequence[TransportResult | Exception]) -> None:
        self._script = list(script)
        self.requests: list[dict[str, Any]] = []

    def complete(self, **kwargs: Any) -> TransportResult:
        self.requests.append(kwargs)
        assert self._script, "FakeTransport script exhausted: the engine made an extra call"
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def remaining(self) -> int:
        return len(self._script)


def success(
    payload: dict[str, Any],
    *,
    raw_text: str | None = None,
    input_tokens: int = 100,
    output_tokens: int = 20,
    cache_creation_tokens: int = 0,
    cache_read_tokens: int = 0,
) -> TransportResult:
    """A well-formed response; `raw_text` defaults to the payload's JSON."""
    return TransportResult(
        payload=payload,
        raw_text=raw_text if raw_text is not None else json.dumps(payload, sort_keys=True),
        stop_reason="end_turn",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation_tokens=cache_creation_tokens,
        cache_read_tokens=cache_read_tokens,
    )


def malformed() -> TransportResult:
    return TransportResult(
        payload=None,
        raw_text=RAW_UNPARSEABLE,
        stop_reason="end_turn",
        input_tokens=100,
        output_tokens=20,
    )


def truncated() -> TransportResult:
    return TransportResult(
        payload=None,
        raw_text='{"label": "hi", "sco',
        stop_reason="max_tokens",
        input_tokens=100,
        output_tokens=20,
    )


def refusal() -> TransportResult:
    return TransportResult(
        payload=None,
        raw_text="",
        stop_reason="refusal",
        input_tokens=100,
        output_tokens=0,
    )
