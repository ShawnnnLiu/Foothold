"""The production Anthropic transport: the ONLY SDK import site in this repo.

Three decisions worth stating (tech reference 4.1):

1. The call requests schema-shaped output through the provider's json_schema
   output format, but returns the RAW parsed dict. Eager SDK-side validation
   would raise inside the SDK call and escape the engine's bounded repair loop,
   so the engine owns validation and repair.
2. Extended thinking is explicitly pinned OFF. On some model tiers, omitting the
   parameter silently enables adaptive thinking whose tokens bill inside
   `max_tokens`, which would truncate small-cap calls. No sampling parameters
   are configured either: several tiers reject non-default values, and output
   comparability rests on prompt-byte pinning instead.
3. The error translation table is defined over `type(exc).__name__` membership
   sets rather than over SDK exception classes, so unit tests can drive it with
   stand-in classes that carry matching names without constructing real SDK
   exceptions (which need an `httpx` request/response pair). The message that
   reaches the log carries the exception TYPE NAME only, never a body: bodies
   may quote request content or credentials.

The client is injected so tests never construct a networked client implicitly;
`build_client` is the production factory and sets `max_retries=0`, because retry
accounting belongs to the engine's inner loop, not to the SDK.
"""

import json
from typing import Any

from anthropic import Anthropic
from anthropic.types import (
    Message,
    MessageParam,
    OutputConfigParam,
    TextBlockParam,
    ThinkingConfigDisabledParam,
)
from pydantic import BaseModel

from starmap.contracts.reason_codes import LlmReasonCode
from starmap.llm.engine import TransportResult
from starmap.llm.errors import TransportError

# Anthropic public pricing for `claude-sonnet-5`, read from the pricing table on
# 2026-07-31: $3.00 per MTok input and $15.00 per MTok output at list price (an
# introductory $2.00 / $10.00 rate runs through 2026-08-31). We estimate against
# list price so the logged cost is never an under-count. These are estimate
# inputs for the call log, not billing facts.
SONNET_5_INPUT_PRICE_PER_MTOK = 3.00
SONNET_5_OUTPUT_PRICE_PER_MTOK = 15.00

AUTH_ERROR_NAMES = frozenset({"AuthenticationError", "PermissionDeniedError"})
RATE_LIMIT_ERROR_NAMES = frozenset({"RateLimitError"})
NON_RETRYABLE_ERROR_NAMES = frozenset(
    {"BadRequestError", "NotFoundError", "UnprocessableEntityError"}
)

# JSON Schema keywords the provider's structured-output format does not accept.
# Pydantic emits them from field constraints, so they are stripped before the
# schema goes on the wire; the engine still enforces every one of them when it
# revalidates the payload through the contract.
UNSUPPORTED_SCHEMA_KEYWORDS = frozenset(
    {
        "exclusiveMaximum",
        "exclusiveMinimum",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "multipleOf",
        "pattern",
        "uniqueItems",
    }
)


def build_client() -> Anthropic:
    """Production client. `max_retries=0`: the engine owns the retry budget."""
    return Anthropic(max_retries=0)


def translate_sdk_error(error: Exception) -> TransportError:
    """Map an SDK exception onto the retryable/permanent taxonomy."""
    name = type(error).__name__
    if name in AUTH_ERROR_NAMES:
        return TransportError(name, retryable=False, reason_code=LlmReasonCode.AUTH_FAILED)
    if name in RATE_LIMIT_ERROR_NAMES:
        return TransportError(name, retryable=True, reason_code=LlmReasonCode.RATE_LIMITED)
    if name in NON_RETRYABLE_ERROR_NAMES:
        return TransportError(name, retryable=False, reason_code=LlmReasonCode.CALL_FAILED)
    # Overloaded, 5xx, connection blips, and timeouts all land here.
    return TransportError(name, retryable=True, reason_code=LlmReasonCode.CALL_FAILED)


def sanitize_schema(node: object) -> object:
    """Strip unsupported keywords and forbid extra properties on every object."""
    if isinstance(node, list):
        return [sanitize_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    cleaned: dict[str, object] = {
        key: sanitize_schema(value)
        for key, value in node.items()
        if key not in UNSUPPORTED_SCHEMA_KEYWORDS
    }
    if cleaned.get("type") == "object":
        cleaned["additionalProperties"] = False
    return cleaned


def build_output_schema(output_contract: type[BaseModel]) -> dict[str, object]:
    """The wire schema for the provider's structured-output format."""
    schema = sanitize_schema(output_contract.model_json_schema(mode="serialization"))
    assert isinstance(schema, dict)
    return schema


def build_user_content(user_prompt: str, repair_suffix: str | None) -> list[TextBlockParam]:
    """One user message, two content blocks.

    The cache breakpoint sits on the BASE PROMPT block, not on `system`:
    providers only cache prefixes above a per-model token minimum that a system
    prompt alone never reaches. Net effect on a repair round, system and base
    prompt are served from cache and only the suffix is re-processed.
    """
    blocks: list[TextBlockParam] = [
        {"type": "text", "text": user_prompt, "cache_control": {"type": "ephemeral"}}
    ]
    if repair_suffix is not None:
        blocks.append({"type": "text", "text": repair_suffix})
    return blocks


def extract_text(message: Message) -> str:
    return "".join(block.text for block in message.content if block.type == "text")


def parse_payload(raw_text: str) -> dict[str, Any] | None:
    """Return the parsed object, or null when the text is not a JSON object."""
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


class AnthropicTransport:
    def __init__(self, client: Anthropic) -> None:
        self._client = client

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
    ) -> TransportResult:
        thinking: ThinkingConfigDisabledParam = {"type": "disabled"}
        output_config: OutputConfigParam = {
            "format": {"type": "json_schema", "schema": build_output_schema(output_contract)}
        }
        messages: list[MessageParam] = [
            {"role": "user", "content": build_user_content(user_prompt, repair_suffix)}
        ]
        try:
            message = self._client.messages.create(
                model=model_name,
                max_tokens=max_tokens,
                system=system,
                thinking=thinking,
                output_config=output_config,
                messages=messages,
                timeout=timeout_seconds,
            )
        except Exception as error:
            raise translate_sdk_error(error) from error

        if not isinstance(message, Message):
            raise TransportError(
                "UnexpectedStreamingResponse",
                retryable=False,
                reason_code=LlmReasonCode.CALL_FAILED,
            )

        raw_text = extract_text(message)
        usage = message.usage
        return TransportResult(
            payload=parse_payload(raw_text),
            raw_text=raw_text,
            # `max_tokens` maps to truncated semantics upstream; the payload may
            # be null when the JSON was cut mid-stream.
            stop_reason=message.stop_reason or "",
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation_tokens=usage.cache_creation_input_tokens or 0,
            cache_read_tokens=usage.cache_read_input_tokens or 0,
        )
