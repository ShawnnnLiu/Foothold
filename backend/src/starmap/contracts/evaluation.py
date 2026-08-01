"""Evaluation contract: the deterministic findings object.

Canonical spec: docs/specs/evaluation.schema.md.
This module is load-bearing twice: it is the wire shape of the Week 2
`POST /api/evaluations` response AND the petition prompt's vocabulary, so the
findings object handed to the prompt IS the object the citation validator
checks the drafted letter against. A letter may only cite what a finding
already carries.

Every value here is produced by deterministic code (`transfer/evaluate.py`);
`detail` is template text, never LLM output. The classification order, units
attribution, and finding sort key live in
docs/implementation-plans/articulation/03-transfer-evaluator.md; this module
holds only the shape and the invariants consumers may rely on.
"""

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from starmap.contracts.agreement import (
    ASSIST_KEY_PATTERN,
    YEAR_LABEL_PATTERN,
    check_consecutive_years,
)
from starmap.contracts.articulation import MAX_UNITS, AdvisementText
from starmap.contracts.base import FROZEN, reject_control_chars
from starmap.contracts.codes import CourseCode
from starmap.contracts.dedup import find_duplicates
from starmap.contracts.reason_codes import BUCKET_FOR_CODE, EvaluationFindingCode, TriageBucket

EVALUATION_ID_PATTERN = r"^eval_[0-9a-f]{16}$"

AgreementKey = Annotated[str, Field(pattern=ASSIST_KEY_PATTERN)]
"""An ASSIST agreement key, the citation a student can paste into assist.org."""

# The partition is normative (spec) and total: the tests assert these two sets
# are disjoint and together cover `EvaluationFindingCode`, so a new code cannot
# ship without a decision about whether it points at a published articulation.
CODES_REQUIRING_CITATION: frozenset[EvaluationFindingCode] = frozenset(
    {
        EvaluationFindingCode.TRANSFERS_CLEAN,
        EvaluationFindingCode.ADVISEMENT_NOTE,
        EvaluationFindingCode.PARTIAL_SERIES,
        EvaluationFindingCode.FUZZY_MATCH,
        EvaluationFindingCode.STALE_YEAR,
        EvaluationFindingCode.DOUBLE_COUNT_RISK,
        EvaluationFindingCode.STILL_OWED,
    }
)
CODES_FORBIDDING_CITATION: frozenset[EvaluationFindingCode] = frozenset(
    {
        EvaluationFindingCode.NO_ARTICULATION,
        EvaluationFindingCode.UNRESOLVED,
    }
)


class StudentCourse(BaseModel):
    """One resolved input course.

    Unresolved input never becomes a `StudentCourse`; it becomes an
    `unresolved` finding instead, so this list is exactly the set of courses
    the evaluator reasoned about.
    """

    model_config = FROZEN

    course_code: CourseCode
    title: str | None = Field(default=None, min_length=1, max_length=300)
    units: float = Field(gt=0, le=MAX_UNITS)
    resolution: Literal["exact", "fuzzy_match"]

    @field_validator("title")
    @classmethod
    def _hygiene(cls, value: str | None) -> str | None:
        return None if value is None else reject_control_chars(value)


class Citation(BaseModel):
    """The ground-truth pointer a finding carries; a partial citation is none."""

    model_config = FROZEN

    assist_key: AgreementKey
    position: int = Field(ge=0)
    year_label: str = Field(pattern=YEAR_LABEL_PATTERN)

    @field_validator("year_label")
    @classmethod
    def _check_years_are_consecutive(cls, value: str) -> str:
        return check_consecutive_years("year_label", value)


class Finding(BaseModel):
    model_config = FROZEN

    code: EvaluationFindingCode
    bucket: TriageBucket
    student_course_codes: list[CourseCode] = Field(default_factory=list)
    receiving_course_code: CourseCode | None = None
    receiving_course_title: str | None = Field(default=None, min_length=1, max_length=300)
    units: float = Field(ge=0)
    citation: Citation | None = None
    advisements: list[AdvisementText] = Field(default_factory=list)
    detail: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("receiving_course_title", "detail")
    @classmethod
    def _hygiene(cls, value: str | None) -> str | None:
        return None if value is None else reject_control_chars(value)

    @model_validator(mode="after")
    def _check_bucket_derivation(self) -> "Finding":
        expected = BUCKET_FOR_CODE[self.code]
        if self.bucket != expected:
            raise ValueError(
                f"bucket {self.bucket.value!r} does not match code {self.code.value!r}; "
                f"expected {expected.value!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_student_course_codes_unique(self) -> "Finding":
        duplicates = find_duplicates(self.student_course_codes)
        if duplicates:
            raise ValueError(f"student_course_codes contains duplicates: {duplicates}")
        return self

    @model_validator(mode="after")
    def _check_citation_matches_code(self) -> "Finding":
        if self.code in CODES_REQUIRING_CITATION and self.citation is None:
            raise ValueError(
                f"citation is required for code {self.code.value!r}, which is a claim about a "
                f"published articulation, but it is null"
            )
        if self.code in CODES_FORBIDDING_CITATION and self.citation is not None:
            raise ValueError(
                f"citation must be null for code {self.code.value!r}, which cites no "
                f"articulation, but it is {self.citation.assist_key!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_advisement_note_carries_text(self) -> "Finding":
        if self.code is EvaluationFindingCode.ADVISEMENT_NOTE and not self.advisements:
            raise ValueError(
                f"code {self.code.value!r} requires a non-empty advisements list; an advisement "
                f"the student cannot read is a silently dropped advisement"
            )
        return self


class UnitsSummary(BaseModel):
    """Bucket totals for the triage header.

    The four unit totals deliberately do not sum to the student's total units:
    `still_owed_units` counts requirement units no student course covers.
    """

    model_config = FROZEN

    clean_units: float = Field(ge=0)
    at_risk_units: float = Field(ge=0)
    no_articulation_units: float = Field(ge=0)
    still_owed_units: float = Field(ge=0)
    at_risk_dollars: float | None = Field(default=None, ge=0)
    no_articulation_dollars: float | None = Field(default=None, ge=0)


class Evaluation(BaseModel):
    model_config = FROZEN

    evaluation_id: str = Field(pattern=EVALUATION_ID_PATTERN)
    sending_institution_id: int = Field(gt=0)
    receiving_institution_id: int = Field(gt=0)
    major_key: AgreementKey
    dept_keys: list[AgreementKey] = Field(default_factory=list)
    year_id: int = Field(gt=0)
    year_label: str = Field(pattern=YEAR_LABEL_PATTERN)
    student_courses: list[StudentCourse] = Field(min_length=1)
    findings: list[Finding] = Field(default_factory=list)
    units: UnitsSummary
    created_at: datetime

    @field_validator("year_label")
    @classmethod
    def _check_years_are_consecutive(cls, value: str) -> str:
        return check_consecutive_years("year_label", value)

    @model_validator(mode="after")
    def _check_institutions_differ(self) -> "Evaluation":
        if self.sending_institution_id == self.receiving_institution_id:
            raise ValueError(
                f"sending_institution_id and receiving_institution_id are both "
                f"{self.sending_institution_id!r}; an evaluation crosses two institutions"
            )
        return self

    @model_validator(mode="after")
    def _check_dept_keys_unique(self) -> "Evaluation":
        duplicates = find_duplicates(self.dept_keys)
        if duplicates:
            raise ValueError(f"dept_keys contains duplicates: {duplicates}")
        return self

    @model_validator(mode="after")
    def _check_student_courses_unique(self) -> "Evaluation":
        duplicates = find_duplicates(course.course_code for course in self.student_courses)
        if duplicates:
            raise ValueError(f"student_courses contains duplicate course codes: {duplicates}")
        return self

    @model_validator(mode="after")
    def _check_created_at_is_tz_aware(self) -> "Evaluation":
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError(
                f"created_at must be timezone-aware, got naive value "
                f"{self.created_at.isoformat()!r}"
            )
        return self
