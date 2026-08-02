"""Articulation contract: one receiving course and its sending-side expression.

Canonical spec: docs/specs/articulation.schema.md.
This is the unit the deterministic evaluator consumes, so it carries its own
citation coordinates (`agreement_id`, `position`) rather than relying on
ambient context.

The agreement-id constants, `GUID_PATTERN`, and `AdvisementText` live here
rather than in `contracts/agreement.py` because doc 01 locks the import
direction as agreement -> articulation (`TemplateCell.course` is a
`ReceivingCourse`), and both modules need them; a single home in the
imported-from module is the only placement without an import cycle.
`agreement.py` owns the behavior that uses them (`derive_agreement_id` and the
coherence validators).
"""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, field_validator, model_validator

from starmap.contracts.articulation_expr import ArticulationExprField
from starmap.contracts.base import FROZEN, reject_control_chars
from starmap.contracts.codes import (
    COURSE_NUMBER_MAX_LENGTH,
    COURSE_NUMBER_PATTERN,
    COURSE_PREFIX_PATTERN,
    CourseCode,
    course_code_from_parts,
)

AGREEMENT_ID_PREFIX = "agr_"
AGREEMENT_ID_HASH_LENGTH = 16
AGREEMENT_ID_PATTERN = rf"^{AGREEMENT_ID_PREFIX}[0-9a-f]{{{AGREEMENT_ID_HASH_LENGTH}}}$"
GUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"

MAX_UNITS = 20.0

AdvisementText = Annotated[
    str,
    Field(min_length=1, max_length=2000),
    AfterValidator(reject_control_chars),
]
"""One advisement string; the 2000 cap matches `NoteLeaf.note` so a text can
move between an advisement list and a note leaf without a length surprise."""


class ReceivingCourse(BaseModel):
    """The receiving-side course, shared with `agreement.TemplateCell`."""

    model_config = FROZEN

    course_code: CourseCode
    prefix: str = Field(min_length=1, max_length=16, pattern=COURSE_PREFIX_PATTERN)
    number: str = Field(
        min_length=1, max_length=COURSE_NUMBER_MAX_LENGTH, pattern=COURSE_NUMBER_PATTERN
    )
    title: str = Field(min_length=1, max_length=300)
    units_min: float = Field(gt=0, le=MAX_UNITS)
    units_max: float = Field(le=MAX_UNITS)

    @field_validator("title")
    @classmethod
    def _hygiene(cls, value: str) -> str:
        return reject_control_chars(value)

    @model_validator(mode="after")
    def _check_units_range(self) -> "ReceivingCourse":
        if self.units_max < self.units_min:
            raise ValueError(f"units_max {self.units_max!r} is below units_min {self.units_min!r}")
        return self

    @model_validator(mode="after")
    def _check_course_code_derivation(self) -> "ReceivingCourse":
        expected = course_code_from_parts(self.prefix, self.number)
        if self.course_code != expected:
            raise ValueError(
                f"course_code {self.course_code!r} does not match prefix {self.prefix!r} "
                f"and number {self.number!r}; expected {expected!r}"
            )
        return self


class Articulation(BaseModel):
    model_config = FROZEN

    agreement_id: str = Field(pattern=AGREEMENT_ID_PATTERN)
    position: int = Field(ge=0)
    template_cell_id: str | None = Field(default=None, pattern=GUID_PATTERN)
    receiving_course: ReceivingCourse
    sending_expr: ArticulationExprField | None = None
    no_articulation_reason: str | None = Field(default=None, min_length=1, max_length=500)
    advisements: list[AdvisementText] = Field(default_factory=list)

    @field_validator("no_articulation_reason")
    @classmethod
    def _hygiene(cls, value: str | None) -> str | None:
        return None if value is None else reject_control_chars(value)

    @model_validator(mode="after")
    def _check_reason_excludes_expr(self) -> "Articulation":
        if self.no_articulation_reason is not None and self.sending_expr is not None:
            raise ValueError(
                f"no_articulation_reason {self.no_articulation_reason!r} cannot coexist with a "
                f"sending_expr; a reason for having no articulation contradicts having one"
            )
        return self
