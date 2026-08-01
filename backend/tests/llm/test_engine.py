"""The engine outcome table, pinned (tech reference 4.1).

Every test runs against FakeTransport with a frozen clock, sequential ids, and a
recording sleeper. Nothing here touches the network.
"""

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from starmap.contracts.reason_codes import LlmReasonCode
from starmap.llm.engine import (
    CLIP_MARKER,
    REPAIR_PREAMBLE,
    AdapterConfig,
    TransportResult,
    estimate_cost_usd,
)
from starmap.llm.errors import GenerationError, TransportError
from tests.llm.conftest import (
    CONFIG,
    CROSS_FIELD_INVALID_PAYLOAD,
    RUN_ID,
    SYSTEM,
    USER_PROMPT,
    VALID_PAYLOAD,
    Answer,
    Harness,
)
from tests.support.transports import FakeTransport, malformed, refusal, success, truncated


def generate(
    harness: Harness,
    transport: FakeTransport,
    *,
    post_validate: Callable[[Answer], None] | None = None,
) -> Answer:
    engine = harness.engine(transport)
    return engine.generate(
        run_id=RUN_ID,
        system=SYSTEM,
        user_prompt=USER_PROMPT,
        post_validate=post_validate,
    )


def retryable(name: str = "OverloadedError") -> TransportError:
    return TransportError(name, retryable=True, reason_code=LlmReasonCode.CALL_FAILED)


# --- inner loop: transport errors -------------------------------------------------


def test_retry_pacing_two_retryable_errors_then_success(harness: Harness) -> None:
    transport = FakeTransport([retryable(), retryable(), success(VALID_PAYLOAD)])

    answer = generate(harness, transport)

    assert answer.label == "low"
    assert harness.sleeper.durations == [1.0, 2.0]
    assert harness.rows() == [
        (0, 0, "fail", "call_failed"),
        (0, 1, "fail", "call_failed"),
        (0, 2, "pass", None),
    ]


def test_non_retryable_error_raises_immediately_with_one_row(harness: Harness) -> None:
    error = TransportError(
        "AuthenticationError", retryable=False, reason_code=LlmReasonCode.AUTH_FAILED
    )
    transport = FakeTransport([error])

    with pytest.raises(GenerationError) as excinfo:
        generate(harness, transport)

    assert excinfo.value.llm_reason_code is LlmReasonCode.AUTH_FAILED
    assert harness.rows() == [(0, 0, "fail", "auth_failed")]
    assert harness.sleeper.durations == []


def test_retryable_error_on_last_retry_raises_retry_limit(harness: Harness) -> None:
    transport = FakeTransport([retryable(), retryable(), retryable()])

    with pytest.raises(GenerationError) as excinfo:
        generate(harness, transport)

    assert excinfo.value.llm_reason_code is LlmReasonCode.RETRY_LIMIT_EXCEEDED
    assert harness.rows() == [
        (0, 0, "fail", "call_failed"),
        (0, 1, "fail", "call_failed"),
        (0, 2, "fail", "retry_limit_exceeded"),
    ]
    assert harness.sleeper.durations == [1.0, 2.0]


def test_transport_failure_row_carries_zero_tokens_and_no_response_hash(
    harness: Harness,
) -> None:
    transport = FakeTransport([retryable(), success(VALID_PAYLOAD, input_tokens=42)])

    generate(harness, transport)

    failure, ok = harness.store.list_for_run(RUN_ID)
    assert (failure.input_tokens, failure.output_tokens) == (0, 0)
    assert failure.cost_estimate_usd == 0.0
    assert failure.response_hash is None
    assert failure.prompt_hash is not None
    assert ok.input_tokens == 42


# --- inner loop: refusal and truncation -------------------------------------------


def test_refusal_raises_with_refusal_flag_and_is_never_retried(harness: Harness) -> None:
    transport = FakeTransport([refusal(), success(VALID_PAYLOAD)])

    with pytest.raises(GenerationError) as excinfo:
        generate(harness, transport)

    assert excinfo.value.llm_reason_code is LlmReasonCode.REFUSAL
    (row,) = harness.store.list_for_run(RUN_ID)
    assert row.refusal is True
    assert row.validation_outcome == "fail"
    assert transport.remaining == 1, "a refusal must not be retried"


def test_transient_truncation_then_success(harness: Harness) -> None:
    transport = FakeTransport([truncated(), success(VALID_PAYLOAD)])

    generate(harness, transport)

    assert harness.rows() == [(0, 0, "fail", "truncated"), (0, 1, "pass", None)]
    assert harness.sleeper.durations == [], "truncation is transient, not backed off"
    assert harness.store.list_for_run(RUN_ID)[0].truncated is True


def test_truncation_on_last_retry_raises_retry_limit(harness: Harness) -> None:
    transport = FakeTransport([truncated(), truncated(), truncated()])

    with pytest.raises(GenerationError) as excinfo:
        generate(harness, transport)

    assert excinfo.value.llm_reason_code is LlmReasonCode.RETRY_LIMIT_EXCEEDED
    assert harness.rows() == [
        (0, 0, "fail", "truncated"),
        (0, 1, "fail", "truncated"),
        (0, 2, "fail", "retry_limit_exceeded"),
    ]


# --- outer loop: repair -----------------------------------------------------------


def test_malformed_payload_repair_lists_required_keys_and_keeps_prompt_stable(
    harness: Harness,
) -> None:
    transport = FakeTransport([malformed(), success(VALID_PAYLOAD)])

    generate(harness, transport)

    first, second = transport.requests
    assert first["repair_suffix"] is None
    suffix = second["repair_suffix"]
    assert suffix.startswith(REPAIR_PREAMBLE)
    assert "malformed_output" in suffix
    # Required top-level keys, not the optional one.
    assert "label" in suffix
    assert "score" in suffix
    assert "note" not in suffix
    # Cache stability: the base prompt is byte-identical across attempts.
    assert second["user_prompt"] == first["user_prompt"]
    assert second["system"] == first["system"]
    assert harness.rows() == [(0, 0, "fail", "malformed_output"), (1, 0, "pass", None)]


def test_schema_rejection_via_cross_field_validator_on_wire_valid_payload(
    harness: Harness,
) -> None:
    """Boundary revalidation: the payload satisfies the wire schema and still fails."""
    transport = FakeTransport([success(CROSS_FIELD_INVALID_PAYLOAD), success(VALID_PAYLOAD)])

    answer = generate(harness, transport)

    assert answer.label == "low"
    suffix = transport.requests[1]["repair_suffix"]
    assert "- field: (root) | constraint: value_error:" in suffix
    assert "label 'high' requires score >= 5" in suffix
    assert harness.rows() == [(0, 0, "fail", "schema_rejected"), (1, 0, "pass", None)]


def test_field_level_rejection_names_the_field_path(harness: Harness) -> None:
    transport = FakeTransport([success({"label": "low", "score": 99}), success(VALID_PAYLOAD)])

    generate(harness, transport)

    suffix = transport.requests[1]["repair_suffix"]
    assert "- field: score | constraint: less_than_equal:" in suffix
    assert "offending value: 99" in suffix


def test_repair_cap_exhaustion_yields_three_attempts_then_typed_error(
    harness: Harness,
) -> None:
    transport = FakeTransport([malformed(), malformed(), malformed()])

    with pytest.raises(GenerationError) as excinfo:
        generate(harness, transport)

    assert excinfo.value.llm_reason_code is LlmReasonCode.REPAIR_LIMIT_EXCEEDED
    assert harness.rows() == [
        (0, 0, "fail", "malformed_output"),
        (1, 0, "fail", "malformed_output"),
        (2, 0, "fail", "malformed_output"),
    ]
    assert len(transport.requests) == 3


def test_worst_case_is_nine_provider_calls_and_nine_rows(harness: Harness) -> None:
    """Budgets compose: 3 repair attempts x 3 provider calls."""
    script: list[TransportResult | Exception] = []
    for _ in range(3):
        script.extend([retryable(), retryable(), success(CROSS_FIELD_INVALID_PAYLOAD)])
    transport = FakeTransport(script)

    with pytest.raises(GenerationError) as excinfo:
        generate(harness, transport)

    assert excinfo.value.llm_reason_code is LlmReasonCode.REPAIR_LIMIT_EXCEEDED
    assert len(transport.requests) == 9
    assert len(harness.store.list_for_run(RUN_ID)) == 9
    assert harness.rows()[-1] == (2, 2, "fail", "schema_rejected")


def test_repair_context_is_replaced_not_accumulated(harness: Harness) -> None:
    transport = FakeTransport([malformed(), success({"label": "", "score": 1}), malformed()])

    with pytest.raises(GenerationError):
        generate(harness, transport)

    third_suffix = transport.requests[2]["repair_suffix"]
    assert third_suffix.count(REPAIR_PREAMBLE) == 1
    assert "malformed_output" not in third_suffix
    assert "- field: label |" in third_suffix


# --- post-validators --------------------------------------------------------------


def test_post_validator_value_error_is_repairable(harness: Harness) -> None:
    calls: list[str] = []

    def post_validate(answer: Answer) -> None:
        calls.append(answer.label)
        if answer.score < 5:
            raise ValueError(f"score {answer.score} is below the demo floor of 5")

    transport = FakeTransport(
        [success(VALID_PAYLOAD), success({"label": "low", "score": 7, "note": None})]
    )

    answer = generate(harness, transport, post_validate=post_validate)

    assert answer.score == 7
    assert calls == ["low", "low"]
    suffix = transport.requests[1]["repair_suffix"]
    assert "post_validate: score 2 is below the demo floor of 5" in suffix
    assert harness.rows() == [(0, 0, "fail", "schema_rejected"), (1, 0, "pass", None)]


def test_post_validator_raising_generation_error_propagates(harness: Harness) -> None:
    """Locked: post-validators must raise `ValueError`.

    A `GenerationError` from a post-validator is a programming error, so the
    engine lets it propagate untouched rather than treating it as repairable.
    """

    def post_validate(answer: Answer) -> None:
        raise GenerationError("wrong error type", reason_code=LlmReasonCode.SCHEMA_REJECTED)

    transport = FakeTransport([success(VALID_PAYLOAD), success(VALID_PAYLOAD)])

    with pytest.raises(GenerationError, match="wrong error type"):
        generate(harness, transport, post_validate=post_validate)

    assert len(transport.requests) == 1, "a programming error must not consume the repair budget"
    assert harness.store.list_for_run(RUN_ID) == []


# --- cost, hashes, and the observability hooks ------------------------------------


def test_cost_formula_spot_values_across_token_classes() -> None:
    # 1_000_000 base input at $3 = $3.00; 1_000_000 cache writes at 1.25x = $3.75;
    # 1_000_000 cache reads at 0.10x = $0.30; 1_000_000 output at $15 = $15.00.
    cost = estimate_cost_usd(
        input_tokens=1_000_000,
        output_tokens=1_000_000,
        cache_creation_tokens=1_000_000,
        cache_read_tokens=1_000_000,
        input_price_per_mtok=3.00,
        output_price_per_mtok=15.00,
    )
    assert cost == pytest.approx(3.00 + 3.75 + 0.30 + 15.00)

    assert estimate_cost_usd(
        input_tokens=0,
        output_tokens=0,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        input_price_per_mtok=3.00,
        output_price_per_mtok=15.00,
    ) == pytest.approx(0.0)


def test_logged_cost_and_cache_hit_reflect_the_response(harness: Harness) -> None:
    transport = FakeTransport(
        [
            success(
                VALID_PAYLOAD,
                input_tokens=1000,
                output_tokens=500,
                cache_creation_tokens=200,
                cache_read_tokens=4000,
            )
        ]
    )

    generate(harness, transport)

    (row,) = harness.store.list_for_run(RUN_ID)
    assert row.cache_hit is True
    expected = ((1000 + 1.25 * 200 + 0.10 * 4000) * 3.00 + 500 * 15.00) / 1e6
    assert row.cost_estimate_usd == pytest.approx(expected)


def test_cache_hit_is_false_without_cache_reads(harness: Harness) -> None:
    transport = FakeTransport([success(VALID_PAYLOAD, cache_creation_tokens=900)])

    generate(harness, transport)

    (row,) = harness.store.list_for_run(RUN_ID)
    assert row.cache_hit is False


def test_log_rows_carry_hashes_only_never_prompt_or_response_text(
    harness: Harness,
) -> None:
    secret_prompt = "SECRET-PROMPT-MARKER"
    secret_response = '{"label": "low", "score": 2, "note": "SECRET-RESPONSE-MARKER"}'
    transport = FakeTransport(
        [success({"label": "low", "score": 2, "note": "x"}, raw_text=secret_response)]
    )
    engine = harness.engine(transport)

    engine.generate(run_id=RUN_ID, system=SYSTEM, user_prompt=secret_prompt)

    (row,) = harness.store.list_for_run(RUN_ID)
    serialized = row.model_dump_json()
    assert secret_prompt not in serialized
    assert "SECRET-RESPONSE-MARKER" not in serialized
    assert row.prompt_hash is not None and len(row.prompt_hash) == 64
    assert row.response_hash is not None and len(row.response_hash) == 64


def test_prompt_hash_covers_the_full_rendered_bytes_including_the_suffix(
    harness: Harness,
) -> None:
    transport = FakeTransport([malformed(), success(VALID_PAYLOAD)])

    generate(harness, transport)

    first, second = harness.store.list_for_run(RUN_ID)
    assert first.prompt_hash != second.prompt_hash


def test_debug_sink_receives_raw_text_and_the_recorder_sees_every_row(
    harness: Harness,
) -> None:
    transport = FakeTransport([retryable(), success(VALID_PAYLOAD, raw_text="RAW-BODY")])

    generate(harness, transport)

    assert harness.raw_sink == ["RAW-BODY"], "the sink is fed only when a response arrived"
    assert harness.recorded == [row.llm_call_log_id for row in harness.store.list_for_run(RUN_ID)]


def test_timeout_and_model_config_pass_through_to_the_transport(harness: Harness) -> None:
    transport = FakeTransport([success(VALID_PAYLOAD)])

    generate(harness, transport)

    request = transport.requests[0]
    assert request["timeout_seconds"] == CONFIG.timeout_seconds
    assert request["model_name"] == CONFIG.model_name
    assert request["max_tokens"] == CONFIG.max_tokens
    assert request["output_contract"] is Answer


def test_clipping_marks_long_offending_values(harness: Harness) -> None:
    """A model-level validator sees the whole object; the re-prompt must not echo it."""
    bulky = {"label": "high", "score": 1, "note": "y" * 400}
    transport = FakeTransport([success(bulky), success(VALID_PAYLOAD)])

    generate(harness, transport)

    suffix = transport.requests[1]["repair_suffix"]
    assert CLIP_MARKER in suffix
    assert "y" * 400 not in suffix


# --- configuration ----------------------------------------------------------------


def test_caps_live_in_field_constraints_and_are_never_clamped() -> None:
    for field, value in [("max_sdk_retries", 3), ("max_repair_attempts", 3)]:
        with pytest.raises(ValidationError, match=field):
            AdapterConfig.model_validate(CONFIG.model_dump() | {field: value})


def test_zero_budgets_mean_one_attempt_and_one_call(harness: Harness) -> None:
    config = AdapterConfig.model_validate(
        CONFIG.model_dump() | {"max_sdk_retries": 0, "max_repair_attempts": 0}
    )
    transport = FakeTransport([malformed()])
    engine = harness.engine(transport, config=config)

    with pytest.raises(GenerationError) as excinfo:
        engine.generate(run_id=RUN_ID, system=SYSTEM, user_prompt=USER_PROMPT)

    assert excinfo.value.llm_reason_code is LlmReasonCode.REPAIR_LIMIT_EXCEEDED
    assert len(transport.requests) == 1


def test_unknown_node_name_is_rejected(harness: Harness) -> None:
    with pytest.raises(ValueError, match="pathway_proposer"):
        harness.engine(FakeTransport([]), node_name="pathway_proposer")
