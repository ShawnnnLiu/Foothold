"""Catalog course contract.

Canonical spec: docs/specs/course.schema.md.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from starmap.contracts.base import FROZEN, reject_control_chars
from starmap.contracts.codes import CourseCode
from starmap.contracts.prereq_expr import PrereqExprField


class Course(BaseModel):
    model_config = FROZEN

    course_code: CourseCode
    title: str = Field(min_length=1, max_length=300)
    points_min: float = Field(gt=0, le=20)
    points_max: float = Field(le=20)
    description: str | None = Field(default=None, min_length=1, max_length=8000)
    prereq_prose: str | None = Field(default=None, min_length=1, max_length=4000)
    prereq_expr: PrereqExprField | None = None
    prereq_confidence: Literal["parsed", "fallback_flat", "none"]
    bulletin_url: str
    department_code: str = Field(min_length=1, max_length=8, pattern=r"^[A-Z]+$")

    @field_validator("title")
    @classmethod
    def _title_hygiene(cls, value: str) -> str:
        return reject_control_chars(value)

    @field_validator("bulletin_url")
    @classmethod
    def _check_url_scheme(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError(f"bulletin_url must start with http:// or https://, got {value!r}")
        return value

    @model_validator(mode="after")
    def _check_points(self) -> "Course":
        if self.points_max < self.points_min:
            raise ValueError(
                f"points_max {self.points_max!r} is less than points_min {self.points_min!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_confidence(self) -> "Course":
        if self.prereq_confidence == "none" and self.prereq_expr is not None:
            raise ValueError("prereq_confidence is 'none' but prereq_expr is not null")
        if self.prereq_confidence != "none" and self.prereq_expr is None:
            raise ValueError(
                f"prereq_confidence is {self.prereq_confidence!r} but prereq_expr is null"
            )
        return self
