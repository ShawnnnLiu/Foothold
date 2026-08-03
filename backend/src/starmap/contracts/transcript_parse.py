"""Transcript-parse contracts: the LLM output shape and the stored artifact.

Canonical spec: docs/specs/transcript_parse.schema.md.
`TranscriptProposal` is the transcript parser's output contract: the course
entries the model read in the pasted text, verbatim. `TranscriptParse` is the
artifact the web seam stores and the client polls; chips carry vocabulary-row
data only, so nothing the model wrote can reach a chip field.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from starmap.contracts.articulation import MAX_UNITS
from starmap.contracts.base import FROZEN, reject_control_chars
from starmap.contracts.codes import CourseCode
from starmap.contracts.dedup import find_duplicates
from starmap.contracts.reason_codes import LlmReasonCode

PARSE_ID_PATTERN = r"^parse_[0-9a-f]{16}$"

# Mirrors `app.web.routes.MAX_COURSES`: the proposal cap and the manual-entry
# cap are the same product limit, sixty courses.
MAX_PROPOSED_COURSES = 60


class ProposedCourse(BaseModel):
    """One course entry as the model read it; verbatim, never normalized.

    `normalize_course_code` would force repair churn on shapes like `MATH20A`
    that resolution handles tolerantly, so `course_code` stays as printed.
    """

    model_config = FROZEN

    course_code: str | None = Field(default=None, min_length=1, max_length=32)
    title: str | None = Field(default=None, min_length=1, max_length=300)
    units: float | None = Field(default=None, gt=0, le=20)
    term: str | None = Field(default=None, min_length=1, max_length=40)

    @field_validator("course_code", "title", "term")
    @classmethod
    def _hygiene(cls, value: str | None) -> str | None:
        return value if value is None else reject_control_chars(value)

    @model_validator(mode="after")
    def _check_code_or_title_present(self) -> "ProposedCourse":
        if self.course_code is None and self.title is None:
            raise ValueError("a proposed course needs a course_code or a title, both are null")
        return self


class TranscriptProposal(BaseModel):
    """The transcript parser's LLM output contract.

    An empty list is a valid read: a pasted page may contain no course lines.
    """

    model_config = FROZEN

    courses: list[ProposedCourse] = Field(max_length=MAX_PROPOSED_COURSES)


class TranscriptChip(BaseModel):
    """One resolved chip; every field comes from the `cc_courses` row."""

    model_config = FROZEN

    course_code: CourseCode
    title: str = Field(min_length=1, max_length=300)
    units_min: float = Field(gt=0, le=MAX_UNITS)
    units_max: float = Field(le=MAX_UNITS)
    resolution: Literal["exact", "fuzzy_match"]

    @field_validator("title")
    @classmethod
    def _hygiene(cls, value: str) -> str:
        return reject_control_chars(value)

    @model_validator(mode="after")
    def _check_units_range(self) -> "TranscriptChip":
        if self.units_max < self.units_min:
            raise ValueError(f"units_max {self.units_max!r} is below units_min {self.units_min!r}")
        return self


class UnresolvedEntry(BaseModel):
    """One verbatim read the vocabulary could not resolve; never a chip."""

    model_config = FROZEN

    proposed_code: str | None = Field(default=None, min_length=1, max_length=32)
    proposed_title: str | None = Field(default=None, min_length=1, max_length=300)

    @field_validator("proposed_code", "proposed_title")
    @classmethod
    def _hygiene(cls, value: str | None) -> str | None:
        return value if value is None else reject_control_chars(value)

    @model_validator(mode="after")
    def _check_code_or_title_present(self) -> "UnresolvedEntry":
        if self.proposed_code is None and self.proposed_title is None:
            raise ValueError(
                "an unresolved entry needs a proposed_code or a proposed_title, both are null"
            )
        return self


class TranscriptParse(BaseModel):
    """The stored and polled transcript-parse artifact."""

    model_config = FROZEN

    parse_id: str = Field(pattern=PARSE_ID_PATTERN)
    sending_institution_id: int = Field(gt=0)
    status: Literal["pending", "succeeded", "failed"]
    reason_code: LlmReasonCode | None = None
    chips: list[TranscriptChip] = Field(default_factory=list)
    unresolved: list[UnresolvedEntry] = Field(default_factory=list)
    created_at: datetime

    @model_validator(mode="after")
    def _check_reason_code_iff_failed(self) -> "TranscriptParse":
        if self.status == "failed" and self.reason_code is None:
            raise ValueError("status 'failed' requires a reason_code, but it is null")
        if self.status != "failed" and self.reason_code is not None:
            raise ValueError(
                f"status {self.status!r} requires reason_code null, but it is "
                f"{self.reason_code.value!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_non_succeeded_emptiness(self) -> "TranscriptParse":
        if self.status == "succeeded":
            return self
        if self.chips:
            raise ValueError(
                f"status {self.status!r} requires chips empty, but it has {len(self.chips)} entries"
            )
        if self.unresolved:
            raise ValueError(
                f"status {self.status!r} requires unresolved empty, but it has "
                f"{len(self.unresolved)} entries"
            )
        return self

    @model_validator(mode="after")
    def _check_chip_codes_unique(self) -> "TranscriptParse":
        duplicates = find_duplicates(chip.course_code for chip in self.chips)
        if duplicates:
            raise ValueError(f"duplicate chip course codes: {duplicates}")
        return self

    @model_validator(mode="after")
    def _check_created_at_is_tz_aware(self) -> "TranscriptParse":
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError(
                f"created_at must be timezone-aware, got naive value "
                f"{self.created_at.isoformat()!r}"
            )
        return self
