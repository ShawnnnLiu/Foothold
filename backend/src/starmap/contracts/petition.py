"""Petition contracts: the LLM output shape and the stored artifact.

Canonical spec: docs/specs/petition.schema.md.
`PetitionDraft` is the petition writer's output contract: one key, the letter,
because every other wire field is computed deterministically. `Petition` is the
artifact the web seam stores and the client polls; its status-shape validators
make the outcome table from docs/implementation-plans/llm-nodes/00-overview.md
decision 4 structurally impossible to misrecord.
"""

from datetime import datetime
from itertools import pairwise
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, Field, model_validator

from starmap.contracts.base import FROZEN, reject_control_chars
from starmap.contracts.codes import CourseCode
from starmap.contracts.evaluation import EVALUATION_ID_PATTERN
from starmap.contracts.reason_codes import LlmReasonCode

PETITION_ID_PATTERN = r"^pet_[0-9a-f]{16}$"

LetterText = Annotated[
    str,
    Field(min_length=200, max_length=8000),
    AfterValidator(reject_control_chars),
]
"""One petition letter. The 200-char floor rejects degenerate output cheaply at
the schema gate, where it produces a repairable violation; hygiene admits the
newlines a letter needs."""


class PetitionDraft(BaseModel):
    """The petition writer's LLM output contract."""

    model_config = FROZEN

    letter_text: LetterText


class CitedCourse(BaseModel):
    """One deterministic letter-to-finding citation the UI renders."""

    model_config = FROZEN

    course_code: CourseCode
    finding_position: int = Field(ge=0)


class Petition(BaseModel):
    """The stored and polled petition artifact."""

    model_config = FROZEN

    petition_id: str = Field(pattern=PETITION_ID_PATTERN)
    evaluation_id: str = Field(pattern=EVALUATION_ID_PATTERN)
    finding_positions: list[Annotated[int, Field(ge=0)]] = Field(min_length=1)
    status: Literal["pending", "succeeded", "failed"]
    reason_code: LlmReasonCode | None = None
    fallback: bool = False
    letter_text: LetterText | None = None
    cited: list[CitedCourse] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def _check_positions_strictly_ascending(self) -> "Petition":
        if any(left >= right for left, right in pairwise(self.finding_positions)):
            raise ValueError(
                f"finding_positions must be strictly ascending, got {self.finding_positions}"
            )
        return self

    @model_validator(mode="after")
    def _check_pending_shape(self) -> "Petition":
        if self.status != "pending":
            return self
        if self.letter_text is not None:
            raise ValueError("status 'pending' requires letter_text null, but a letter is present")
        if self.cited:
            raise ValueError(
                f"status 'pending' requires cited empty, but it has {len(self.cited)} entries"
            )
        if self.fallback:
            raise ValueError("status 'pending' requires fallback false, but it is true")
        if self.reason_code is not None:
            raise ValueError(
                f"status 'pending' requires reason_code null, but it is {self.reason_code.value!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_succeeded_shape(self) -> "Petition":
        if self.status != "succeeded":
            return self
        if self.letter_text is None:
            raise ValueError("status 'succeeded' requires letter_text, but it is null")
        if self.fallback and self.reason_code is None:
            raise ValueError(
                "fallback is true, which requires a reason_code recording why the LLM draft "
                "was discarded, but it is null"
            )
        if not self.fallback and self.reason_code is not None:
            raise ValueError(
                f"reason_code must be null when fallback is false, but it is "
                f"{self.reason_code.value!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_failed_shape(self) -> "Petition":
        if self.status != "failed":
            return self
        if self.letter_text is not None:
            raise ValueError("status 'failed' requires letter_text null, but a letter is present")
        if self.cited:
            raise ValueError(
                f"status 'failed' requires cited empty, but it has {len(self.cited)} entries"
            )
        if self.fallback:
            raise ValueError("status 'failed' requires fallback false, but it is true")
        if self.reason_code is None:
            raise ValueError("status 'failed' requires a reason_code, but it is null")
        return self

    @model_validator(mode="after")
    def _check_cited_positions_selected(self) -> "Petition":
        selected = set(self.finding_positions)
        unselected = [
            entry.finding_position for entry in self.cited if entry.finding_position not in selected
        ]
        if unselected:
            raise ValueError(
                f"cited references finding positions {unselected} that are not in "
                f"finding_positions {self.finding_positions}"
            )
        return self

    @model_validator(mode="after")
    def _check_created_at_is_tz_aware(self) -> "Petition":
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError(
                f"created_at must be timezone-aware, got naive value "
                f"{self.created_at.isoformat()!r}"
            )
        return self
