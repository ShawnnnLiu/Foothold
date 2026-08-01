"""Institution contract: one endpoint of the CCC -> UC/CSU corridor.

Canonical spec: docs/specs/institution.schema.md.
The ASSIST institution id is the sole identifier; `code` arrives space-padded
in the payload, so the strip and the `kind` derivation happen in
`assist/normalize.py` and this contract only accepts the normalized row.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from starmap.contracts.base import FROZEN, reject_control_chars

InstitutionKind = Literal["cc", "uc", "csu"]


class Institution(BaseModel):
    model_config = FROZEN

    assist_id: int = Field(gt=0)
    code: str = Field(min_length=1, max_length=8, pattern=r"^[A-Z][A-Z0-9]{0,7}$")
    name: str = Field(min_length=1, max_length=200)
    kind: InstitutionKind

    @field_validator("name")
    @classmethod
    def _hygiene(cls, value: str) -> str:
        return reject_control_chars(value)
