"""Layer 1 of prompt-version pinning (tech reference 4.6).

`prompt_version` is a hand-maintained label with no structural link to the
prompt bytes. Without a pin, editing a system prompt without bumping the version
would silently mislabel every call-log row and every eval comparison. An
intentional prompt change must bump the version AND replace the pinned hash in
the same commit.

The table is seeded empty: increment 4 ships the scaffold, and the node
increments add one row per system-prompt constant. Layer 2 (the full rendered
prompt, repair suffix included) lives in `tests/support/prompt_pins.py`.
"""

from typing import NamedTuple

import pytest

from starmap.common.ids import sha256_hex
from starmap.llm.petition_writer import PETITION_WRITER_SYSTEM
from starmap.llm.transcript_parser import TRANSCRIPT_PARSER_SYSTEM


class PromptPin(NamedTuple):
    constant_name: str
    prompt: str
    pinned_version: str
    pinned_sha256: str


# One row per system-prompt constant; the node increments each add theirs.
SYSTEM_PROMPT_PINS: tuple[PromptPin, ...] = (
    PromptPin(
        "PETITION_WRITER_SYSTEM",
        PETITION_WRITER_SYSTEM,
        "petition-writer-v1",
        "edfa3abe661d0b80db2ed1824b0224c82ea39c5092c15b1467bd704eeb8696ce",
    ),
    PromptPin(
        "TRANSCRIPT_PARSER_SYSTEM",
        TRANSCRIPT_PARSER_SYSTEM,
        "transcript-parser-v1",
        "63b51c1e7fac49bccbc0d425b9f7fc379fa36192b9e1f36e89f7615d3dba89b9",
    ),
)


@pytest.mark.parametrize("pin", SYSTEM_PROMPT_PINS, ids=lambda pin: pin.constant_name)
def test_system_prompt_matches_its_pin(pin: PromptPin) -> None:
    actual = sha256_hex(pin.prompt)
    assert actual == pin.pinned_sha256, (
        f"{pin.constant_name} changed. If the change is intentional, bump the prompt "
        f"version past {pin.pinned_version!r} and replace the pin in the same commit."
        f"\nnew sha256: {actual}"
    )


def test_pinned_constant_names_are_unique() -> None:
    names = [pin.constant_name for pin in SYSTEM_PROMPT_PINS]
    assert len(names) == len(set(names))
