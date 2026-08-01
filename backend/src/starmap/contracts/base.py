"""Contract conventions machinery shared by every contract model.

Every contract model, nested models included, uses `FROZEN`
(`extra="forbid"`, `frozen=True`); updates rebuild through full validation
via `rebuild`, never `model_copy(update=...)`.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict

FROZEN = ConfigDict(extra="forbid", frozen=True)


def rebuild[T: BaseModel](model: T, **updates: Any) -> T:
    """The only sanctioned update path: every invariant re-runs."""
    return type(model).model_validate(model.model_dump() | updates)


def reject_control_chars(value: str) -> str:
    """Reject codepoints below 0x20 except newline, carriage return, and tab.

    Shared by every text field with control-character hygiene; the offending
    codepoint is reported as U+XXXX.
    """
    for char in value:
        if ord(char) < 0x20 and char not in "\n\r\t":
            raise ValueError(f"contains control character U+{ord(char):04X}")
    return value
