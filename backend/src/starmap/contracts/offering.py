"""Term-offering contract.

Canonical spec: docs/specs/offering.schema.md.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from starmap.contracts.base import FROZEN
from starmap.contracts.codes import CourseCode
from starmap.contracts.dedup import find_duplicates

InstructorName = Annotated[str, Field(min_length=1, max_length=100)]


class Offering(BaseModel):
    model_config = FROZEN

    course_code: CourseCode
    term: Literal["fall", "spring", "summer"]
    year: int = Field(ge=2020, le=2035)
    instructors: list[InstructorName]

    @model_validator(mode="after")
    def _check_instructor_uniqueness(self) -> "Offering":
        duplicates = find_duplicates(self.instructors)
        if duplicates:
            raise ValueError(f"instructors contains case-insensitive duplicates: {duplicates!r}")
        return self
