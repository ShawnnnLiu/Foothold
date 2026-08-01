"""Self-test for the layer-2 prompt-pin harness.

The harness is generic; the node increments instantiate it. This exercises it
against the toy contract so a rot in the harness itself cannot hide until then.
"""

from collections.abc import Mapping
from typing import Any

import pytest

from starmap.common.ids import sha256_hex
from starmap.llm.engine import REPAIR_PREAMBLE
from tests.llm.conftest import RUN_ID, SYSTEM, USER_PROMPT, Harness
from tests.support.prompt_pins import (
    assert_prompt_pin,
    capture_prompt_frames,
    render_prompt_frames,
)
from tests.support.transports import FakeTransport, malformed, success

PAYLOAD = {"label": "low", "score": 2, "note": None}
SECRET_PASTED_TEXT = "PASTED-TRANSCRIPT-THAT-MUST-NOT-BE-PROMPTED"


def frames_for(harness: Harness) -> str:
    def run(transport: FakeTransport) -> object:
        engine = harness.engine(transport)
        return engine.generate(run_id=RUN_ID, system=SYSTEM, user_prompt=USER_PROMPT)

    return capture_prompt_frames(run, [malformed(), success(PAYLOAD)])


def test_frames_capture_both_calls_and_the_real_repair_suffix(harness: Harness) -> None:
    frames = frames_for(harness)

    assert frames.count("### frame ") == 2
    assert "--- repair_suffix ---\n(none)" in frames
    assert REPAIR_PREAMBLE.strip() in frames
    assert "malformed_output" in frames


def test_pin_passes_on_the_current_render_and_reports_the_new_hash(harness: Harness) -> None:
    frames = frames_for(harness)

    assert_prompt_pin(
        frames,
        pinned_sha256=sha256_hex(frames),
        must_contain=[SYSTEM, USER_PROMPT],
        must_exclude=[SECRET_PASTED_TEXT],
    )


def test_pin_fails_loudly_when_the_render_changes(harness: Harness) -> None:
    frames = frames_for(harness)

    with pytest.raises(AssertionError, match="new sha256: "):
        assert_prompt_pin(frames, pinned_sha256="0" * 64)


def test_rot_guards_fire_before_the_hash(harness: Harness) -> None:
    frames = frames_for(harness)

    with pytest.raises(AssertionError, match="no longer contains required block"):
        assert_prompt_pin(frames, pinned_sha256="0" * 64, must_contain=["A LABELED BLOCK"])

    with pytest.raises(AssertionError, match="leaked excluded block"):
        assert_prompt_pin(frames, pinned_sha256="0" * 64, must_exclude=[USER_PROMPT])


def test_render_is_stable_across_runs(harness: Harness) -> None:
    requests: list[Mapping[str, Any]] = [
        {"system": "S", "user_prompt": "U", "repair_suffix": None},
        {"system": "S", "user_prompt": "U", "repair_suffix": "R"},
    ]

    assert render_prompt_frames(requests) == render_prompt_frames(requests)


def test_a_single_call_script_is_rejected(harness: Harness) -> None:
    def run(transport: FakeTransport) -> object:
        engine = harness.engine(transport)
        return engine.generate(run_id=RUN_ID, system=SYSTEM, user_prompt=USER_PROMPT)

    with pytest.raises(AssertionError, match="at least two calls"):
        capture_prompt_frames(run, [success(PAYLOAD)])
