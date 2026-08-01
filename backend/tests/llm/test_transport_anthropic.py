"""The Anthropic transport, exercised only by unit tests: zero network.

The SDK client object is replaced with a stand-in that records the request
kwargs, so block assembly and response normalization are asserted directly. The
error translation table is asserted through stand-in classes whose NAMES match
the SDK's, which is exactly why the table is defined over `type(exc).__name__`.
"""

from typing import Any

import pytest
from anthropic.types import Message, StopReason, TextBlock, Usage
from pydantic import BaseModel, Field

from starmap.contracts.reason_codes import LlmReasonCode
from starmap.llm.errors import TransportError
from starmap.llm.transport_anthropic import (
    AnthropicTransport,
    build_output_schema,
    build_user_content,
    parse_payload,
    sanitize_schema,
    translate_sdk_error,
)


class Answer(BaseModel):
    label: str = Field(min_length=1, max_length=40, pattern=r"^[a-z]+$")
    score: int = Field(ge=0, le=10)
    tags: list[str] = Field(default_factory=list, max_length=3)


def message(text: str, *, stop_reason: StopReason = "end_turn") -> Message:
    return Message(
        id="msg_1",
        content=[TextBlock(type="text", text=text)],
        model="claude-sonnet-5",
        role="assistant",
        stop_reason=stop_reason,
        type="message",
        usage=Usage(
            input_tokens=1200,
            output_tokens=340,
            cache_creation_input_tokens=10,
            cache_read_input_tokens=800,
        ),
    )


class StubMessages:
    def __init__(self, result: Message | Exception) -> None:
        self._result = result
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Message:
        self.calls.append(kwargs)
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


class StubClient:
    def __init__(self, result: Message | Exception) -> None:
        self.messages = StubMessages(result)


def transport_for(result: Message | Exception) -> tuple[AnthropicTransport, StubClient]:
    client = StubClient(result)
    return AnthropicTransport(client), client  # type: ignore[arg-type]


def complete(transport: AnthropicTransport, **overrides: Any) -> Any:
    kwargs: dict[str, Any] = {
        "model_name": "claude-sonnet-5",
        "max_tokens": 2000,
        "system": "SYSTEM",
        "user_prompt": "PROMPT",
        "output_contract": Answer,
        "repair_suffix": None,
        "timeout_seconds": 300.0,
    }
    return transport.complete(**(kwargs | overrides))


# --- error translation ------------------------------------------------------------


class AuthenticationError(Exception): ...


class PermissionDeniedError(Exception): ...


class RateLimitError(Exception): ...


class BadRequestError(Exception): ...


class NotFoundError(Exception): ...


class UnprocessableEntityError(Exception): ...


class InternalServerError(Exception): ...


class APIConnectionError(Exception): ...


class APITimeoutError(Exception): ...


@pytest.mark.parametrize(
    ("error", "retryable", "reason_code"),
    [
        (AuthenticationError(), False, LlmReasonCode.AUTH_FAILED),
        (PermissionDeniedError(), False, LlmReasonCode.AUTH_FAILED),
        (RateLimitError(), True, LlmReasonCode.RATE_LIMITED),
        (BadRequestError(), False, LlmReasonCode.CALL_FAILED),
        (NotFoundError(), False, LlmReasonCode.CALL_FAILED),
        (UnprocessableEntityError(), False, LlmReasonCode.CALL_FAILED),
        (InternalServerError(), True, LlmReasonCode.CALL_FAILED),
        (APIConnectionError(), True, LlmReasonCode.CALL_FAILED),
        (APITimeoutError(), True, LlmReasonCode.CALL_FAILED),
    ],
    ids=lambda value: type(value).__name__ if isinstance(value, Exception) else str(value),
)
def test_error_translation_table(
    error: Exception, retryable: bool, reason_code: LlmReasonCode
) -> None:
    translated = translate_sdk_error(error)
    assert translated.retryable is retryable
    assert translated.llm_reason_code is reason_code


def test_translated_message_carries_the_type_name_only() -> None:
    error = BadRequestError("api key sk-secret rejected for prompt 'confidential'")
    translated = translate_sdk_error(error)
    assert translated.message == "BadRequestError"
    assert "secret" not in translated.message
    assert "confidential" not in translated.message


def test_sdk_errors_surface_as_transport_errors() -> None:
    transport, _ = transport_for(RateLimitError("slow down"))

    with pytest.raises(TransportError) as excinfo:
        complete(transport)

    assert excinfo.value.retryable is True
    assert excinfo.value.llm_reason_code is LlmReasonCode.RATE_LIMITED


# --- request assembly -------------------------------------------------------------


def test_base_prompt_block_carries_the_cache_breakpoint() -> None:
    blocks = build_user_content("PROMPT", None)
    assert blocks == [{"type": "text", "text": "PROMPT", "cache_control": {"type": "ephemeral"}}]


def test_repair_suffix_travels_as_a_separate_uncached_block() -> None:
    blocks = build_user_content("PROMPT", "SUFFIX")
    assert len(blocks) == 2
    assert blocks[0]["text"] == "PROMPT"
    assert blocks[0]["cache_control"] == {"type": "ephemeral"}
    assert blocks[1] == {"type": "text", "text": "SUFFIX"}
    assert "cache_control" not in blocks[1]


def test_request_disables_thinking_and_sets_no_sampling_parameters() -> None:
    transport, client = transport_for(message('{"label": "low", "score": 2}'))

    complete(transport, repair_suffix="SUFFIX", timeout_seconds=42.0)

    (call,) = client.messages.calls
    assert call["thinking"] == {"type": "disabled"}
    assert not {"temperature", "top_p", "top_k"} & set(call)
    assert call["model"] == "claude-sonnet-5"
    assert call["max_tokens"] == 2000
    assert call["system"] == "SYSTEM"
    assert call["timeout"] == 42.0
    assert call["output_config"]["format"]["type"] == "json_schema"
    assert call["messages"] == [{"role": "user", "content": build_user_content("PROMPT", "SUFFIX")}]


def test_output_schema_strips_unsupported_keywords_and_forbids_extras() -> None:
    schema = build_output_schema(Answer)

    label = schema["properties"]["label"]  # type: ignore[index]
    assert label == {"title": "Label", "type": "string"}
    assert schema["additionalProperties"] is False
    assert "maxItems" not in schema["properties"]["tags"]  # type: ignore[index]


def test_sanitize_schema_recurses_through_lists_and_nested_objects() -> None:
    raw = {
        "type": "object",
        "properties": {
            "child": {"type": "object", "properties": {"n": {"type": "integer", "minimum": 1}}}
        },
        "anyOf": [{"type": "object", "minLength": 2}],
    }

    cleaned = sanitize_schema(raw)

    assert cleaned == {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "child": {
                "type": "object",
                "additionalProperties": False,
                "properties": {"n": {"type": "integer"}},
            }
        },
        "anyOf": [{"type": "object", "additionalProperties": False}],
    }


# --- response normalization -------------------------------------------------------


def test_successful_response_normalizes_tokens_and_payload() -> None:
    transport, _ = transport_for(message('{"label": "low", "score": 2}'))

    result = complete(transport)

    assert result.payload == {"label": "low", "score": 2}
    assert result.raw_text == '{"label": "low", "score": 2}'
    assert result.stop_reason == "end_turn"
    assert (result.input_tokens, result.output_tokens) == (1200, 340)
    assert (result.cache_creation_tokens, result.cache_read_tokens) == (10, 800)


def test_unparseable_response_yields_a_null_payload() -> None:
    transport, _ = transport_for(message("I cannot comply."))

    result = complete(transport)

    assert result.payload is None
    assert result.raw_text == "I cannot comply."


def test_truncated_response_keeps_the_stop_reason() -> None:
    transport, _ = transport_for(message('{"label": "lo', stop_reason="max_tokens"))

    result = complete(transport)

    assert result.stop_reason == "max_tokens"
    assert result.payload is None


@pytest.mark.parametrize("raw", ["[1, 2]", '"a string"', "null", "not json"])
def test_non_object_json_is_not_a_payload(raw: str) -> None:
    assert parse_payload(raw) is None
