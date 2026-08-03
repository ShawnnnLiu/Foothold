"""The curated cost table: `data/curated/costs.json` (doc 03, "Cost table").

`CostTable` is deliberately transfer-local rather than a `contracts/` wire
contract: only `transfer/` consumes it, it never crosses an LLM boundary or a
region seam, and it carries no spec doc for the same reason (the decision is
recorded here per doc 03).

The FIGURES are a user gate (overview doc, "Permission gates"): every number
in the file traces to a source URL the user confirmed in-session, including
the well-known California CC per-unit fee. No invented numbers.

Dollar semantics, locked in doc 03: lost or risky units must be retaken at
the TARGET's per-unit price, so `target_per_unit` keys receiving institution
ids and a missing row means "we do not know" (both dollar fields None), never
zero.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from starmap.contracts.base import FROZEN, reject_control_chars


class CostSource(BaseModel):
    """One dated source URL a figure in the table traces to."""

    model_config = FROZEN

    url: str = Field(min_length=1, max_length=500)
    note: str = Field(min_length=1, max_length=500)
    retrieved: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("url", "note")
    @classmethod
    def _hygiene(cls, value: str) -> str:
        return reject_control_chars(value)


class CostTable(BaseModel):
    """The curated per-unit cost table, mirroring the locked file shape."""

    model_config = FROZEN

    version: Literal["costs-v1"]
    sources: list[CostSource] = Field(min_length=1)
    cc_per_unit_default: float = Field(ge=0)
    target_per_unit: dict[str, float]

    @field_validator("target_per_unit")
    @classmethod
    def _keys_are_institution_ids(cls, value: dict[str, float]) -> dict[str, float]:
        for key, rate in value.items():
            if not key.isdigit() or int(key) <= 0:
                raise ValueError(f"target_per_unit key {key!r} is not a positive institution id")
            if rate < 0:
                raise ValueError(f"target_per_unit[{key!r}] is negative: {rate}")
        return value

    def target_rate(self, receiving_id: int) -> float | None:
        """The target's per-unit rate, or None when the table has no row."""
        return self.target_per_unit.get(str(receiving_id))


def load_cost_table(path: Path) -> CostTable:
    """Load and validate the curated file; invalid content fails loudly."""
    return CostTable.model_validate(json.loads(path.read_text(encoding="utf-8")))
