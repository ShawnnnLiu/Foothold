"""Community-college course projection: the sending-side vocabulary.

Canonical spec: docs/specs/cc_course.schema.md.
One projection, three consumers - UI autocomplete, transcript resolution, and
the FTS5 index rows all read these rows - so the code-derivation validator is
what keeps the vocabulary gate structural rather than procedural.

Field-for-field identical to `target_course.TargetCourse` by a locked
decision: duplication over inheritance, matching the house no-hierarchy style.
`test_target_course.py` asserts the two field sets still match.

`MAX_UNITS` is imported from `contracts/articulation.py`, the module that
first needed it, for the same reason `agreement.py` imports its id patterns
from there: one home per shared constant, and the import direction stays
acyclic.
"""

from pydantic import BaseModel, Field, field_validator, model_validator

from starmap.contracts.articulation import MAX_UNITS
from starmap.contracts.base import FROZEN, reject_control_chars
from starmap.contracts.codes import (
    COURSE_NUMBER_PATTERN,
    COURSE_PREFIX_PATTERN,
    CourseCode,
    course_code_from_parts,
)


class CcCourse(BaseModel):
    model_config = FROZEN

    institution_id: int = Field(gt=0)
    course_code: CourseCode
    prefix: str = Field(min_length=1, max_length=16, pattern=COURSE_PREFIX_PATTERN)
    number: str = Field(min_length=1, max_length=8, pattern=COURSE_NUMBER_PATTERN)
    title: str = Field(min_length=1, max_length=300)
    units_min: float = Field(gt=0, le=MAX_UNITS)
    units_max: float = Field(le=MAX_UNITS)

    @field_validator("title")
    @classmethod
    def _hygiene(cls, value: str) -> str:
        return reject_control_chars(value)

    @model_validator(mode="after")
    def _check_units_range(self) -> "CcCourse":
        if self.units_max < self.units_min:
            raise ValueError(f"units_max {self.units_max!r} is below units_min {self.units_min!r}")
        return self

    @model_validator(mode="after")
    def _check_course_code_derivation(self) -> "CcCourse":
        expected = course_code_from_parts(self.prefix, self.number)
        if self.course_code != expected:
            raise ValueError(
                f"course_code {self.course_code!r} does not match prefix {self.prefix!r} "
                f"and number {self.number!r}; expected {expected!r}"
            )
        return self
