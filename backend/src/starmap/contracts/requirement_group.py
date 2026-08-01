"""Requirement-group contract.

Canonical spec: docs/specs/requirement_group.schema.md.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from starmap.common.ids import sha256_hex
from starmap.contracts.base import FROZEN
from starmap.contracts.codes import CourseCode
from starmap.contracts.dedup import find_duplicates


class RequirementGroup(BaseModel):
    model_config = FROZEN

    requirement_group_id: str = Field(pattern=r"^rg_[0-9a-f]{16}$")
    major_id: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9-]+$")
    name: str = Field(min_length=1, max_length=200)
    rule_kind: Literal["all", "choose_n", "note"]
    member_courses: list[CourseCode]
    choose_n: int | None = None
    note_text: str | None = Field(default=None, min_length=1, max_length=1000)

    @model_validator(mode="after")
    def _check_id_derivation(self) -> "RequirementGroup":
        derived = "rg_" + sha256_hex(f"{self.major_id}\n{self.name}")[:16]
        if self.requirement_group_id != derived:
            raise ValueError(
                f"requirement_group_id {self.requirement_group_id!r} does not match "
                f"the derived id {derived!r} for major_id {self.major_id!r} "
                f"and name {self.name!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_member_uniqueness(self) -> "RequirementGroup":
        duplicates = find_duplicates(self.member_courses)
        if duplicates:
            raise ValueError(f"member_courses contains duplicates: {duplicates!r}")
        return self

    @model_validator(mode="after")
    def _check_kind_conditions(self) -> "RequirementGroup":
        if self.rule_kind == "all":
            if self.choose_n is not None:
                raise ValueError("rule_kind 'all' forbids choose_n")
            if self.note_text is not None:
                raise ValueError("rule_kind 'all' forbids note_text")
            if not self.member_courses:
                raise ValueError("rule_kind 'all' requires non-empty member_courses")
        elif self.rule_kind == "choose_n":
            if self.note_text is not None:
                raise ValueError("rule_kind 'choose_n' forbids note_text")
            if self.choose_n is None or not 1 <= self.choose_n <= len(self.member_courses):
                raise ValueError(
                    f"rule_kind 'choose_n' requires choose_n between 1 and "
                    f"{len(self.member_courses)} (the member_courses count), "
                    f"got {self.choose_n!r}"
                )
        else:
            if self.note_text is None:
                raise ValueError("rule_kind 'note' requires note_text")
            if self.choose_n is not None:
                raise ValueError("rule_kind 'note' forbids choose_n")
        return self
