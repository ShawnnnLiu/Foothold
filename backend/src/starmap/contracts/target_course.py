"""Receiving-institution course projection: the target-side vocabulary.

Canonical spec: docs/specs/target_course.schema.md.
The target-side counterpart of `cc_course.CcCourse`: the vocabulary for naming
what a student still owes and what a finding points at, and the set Mode B's
arbitrage inverts back onto community-college courses.

Field-for-field identical to `CcCourse` by a locked decision: duplication over
inheritance, so a receiving-side field can later appear here without leaking
into the sending-side projection. `test_target_course.py` asserts the two
field sets still match, so the duplication cannot drift unnoticed.
"""

from pydantic import BaseModel, Field, field_validator, model_validator

from starmap.contracts.articulation import MAX_UNITS
from starmap.contracts.base import FROZEN, reject_control_chars
from starmap.contracts.codes import (
    COURSE_NUMBER_MAX_LENGTH,
    COURSE_NUMBER_PATTERN,
    COURSE_PREFIX_PATTERN,
    CourseCode,
    course_code_from_parts,
)


class TargetCourse(BaseModel):
    model_config = FROZEN

    institution_id: int = Field(gt=0)
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
    def _check_units_range(self) -> "TargetCourse":
        if self.units_max < self.units_min:
            raise ValueError(f"units_max {self.units_max!r} is below units_min {self.units_min!r}")
        return self

    @model_validator(mode="after")
    def _check_course_code_derivation(self) -> "TargetCourse":
        expected = course_code_from_parts(self.prefix, self.number)
        if self.course_code != expected:
            raise ValueError(
                f"course_code {self.course_code!r} does not match prefix {self.prefix!r} "
                f"and number {self.number!r}; expected {expected!r}"
            )
        return self
