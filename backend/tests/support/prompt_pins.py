"""Layer-2 prompt pinning: the full-rendered-prompt harness (tech reference 4.6).

`prompt_version` is a hand-maintained label with no structural link to the
bytes; without pins, an edit without a version bump would silently mislabel
every call-log row.

Layer 1 (`backend/tests/test_prompt_pins.py`) hashes each system-prompt
constant. Layer 2 is here: run a node against a `FakeTransport` scripted so the
FIRST response deliberately fails a deterministic check, so the second call
carries a real repair suffix and the repair-formatting bytes land inside the
hash. Every outbound `(system, user_prompt, repair_suffix)` frame is serialized
into one canonical text and sha256-pinned.

The rot guards matter as much as the hash: a refactor that silently dropped a
labeled block would otherwise hide behind a stable-but-meaningless hash, so each
pin also asserts which blocks the render must contain and which it must exclude
(a pasted transcript, for instance, must never reach the petition prompt).

This module is generic on purpose; increment 5 instantiates it per node.
"""

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from starmap.common.ids import sha256_hex
from starmap.llm.engine import TransportResult
from tests.support.transports import FakeTransport

FRAME_SEPARATOR = "\n" + "=" * 60 + "\n"


def render_prompt_frames(requests: Sequence[Mapping[str, Any]]) -> str:
    """Serialize every recorded outbound call into one canonical text."""
    frames = []
    for index, request in enumerate(requests):
        suffix = request.get("repair_suffix")
        frames.append(
            f"### frame {index}\n"
            f"--- system ---\n{request['system']}\n"
            f"--- user_prompt ---\n{request['user_prompt']}\n"
            f"--- repair_suffix ---\n{'(none)' if suffix is None else suffix}"
        )
    return FRAME_SEPARATOR.join(frames) + "\n"


def capture_prompt_frames(
    run: Callable[[FakeTransport], object],
    script: Sequence[TransportResult | Exception],
) -> str:
    """Run a node against a scripted transport and return the canonical frame text.

    `script` must start with a response that fails a deterministic check, so the
    repair suffix is exercised.
    """
    transport = FakeTransport(script)
    run(transport)
    assert len(transport.requests) >= 2, (
        "the prompt-pin script must produce at least two calls, so a real repair "
        "suffix is inside the pinned bytes"
    )
    return render_prompt_frames(transport.requests)


def assert_prompt_pin(
    frames: str,
    *,
    pinned_sha256: str,
    must_contain: Sequence[str] = (),
    must_exclude: Sequence[str] = (),
) -> None:
    """Assert the rot guards, then the hash; print the new hash on mismatch."""
    for block in must_contain:
        assert block in frames, f"rendered prompt no longer contains required block {block!r}"
    for block in must_exclude:
        assert block not in frames, f"rendered prompt leaked excluded block {block!r}"
    actual = sha256_hex(frames)
    assert actual == pinned_sha256, (
        "rendered prompt changed. If the change is intentional, bump prompt_version "
        f"and replace the pin in the same commit.\nnew sha256: {actual}"
    )
