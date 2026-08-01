"""Prereq expression tree: recursive discriminated union.

Canonical spec: docs/specs/prereq_expr.schema.md.
Members are structurally discriminated by their distinct required keys
(`all`, `any`, `course`, `note`); `parse_prereq_expr` owns the dispatch.
Consumers type expression fields as the union with a `BeforeValidator`
calling `parse_prereq_expr`.
"""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, RootModel, field_validator, model_validator

from starmap.contracts.base import FROZEN, reject_control_chars
from starmap.contracts.codes import CourseCode

MAX_DEPTH = 3


def parse_prereq_expr(data: object) -> object:
    """Dispatch a mapping to its union member by discriminating key."""
    if isinstance(data, AllOf | AnyOf | CourseLeaf | NoteLeaf):
        return data
    if not isinstance(data, dict):
        raise ValueError(f"prereq expression must be a mapping, got {type(data).__name__}")
    if "all" in data:
        return AllOf.model_validate(data)
    if "any" in data:
        return AnyOf.model_validate(data)
    if "course" in data:
        return CourseLeaf.model_validate(data)
    if "note" in data:
        return NoteLeaf.model_validate(data)
    raise ValueError(
        "prereq expression must contain one of the keys 'all', 'any', 'course', 'note'"
    )


class CourseLeaf(BaseModel):
    model_config = FROZEN

    course: CourseCode
    equivalent_ok: bool = False


class NoteLeaf(BaseModel):
    model_config = FROZEN

    note: str = Field(min_length=1, max_length=500)

    @field_validator("note")
    @classmethod
    def _hygiene(cls, value: str) -> str:
        return reject_control_chars(value)


class AllOf(BaseModel):
    model_config = FROZEN

    all: "list[PrereqExprField]" = Field(min_length=1)

    @model_validator(mode="after")
    def _check_depth(self) -> "AllOf":
        _validate_depth(self)
        return self


class AnyOf(BaseModel):
    model_config = FROZEN

    any: "list[PrereqExprField]" = Field(min_length=1)

    @model_validator(mode="after")
    def _check_depth(self) -> "AnyOf":
        _validate_depth(self)
        return self


PrereqExpr = AllOf | AnyOf | CourseLeaf | NoteLeaf
PrereqExprField = Annotated[PrereqExpr, BeforeValidator(parse_prereq_expr)]


def expr_depth(expr: PrereqExpr) -> int:
    """Nesting depth: a bare leaf is depth 1 and each group level adds 1."""
    if isinstance(expr, AllOf):
        children: list[PrereqExpr] = expr.all
    elif isinstance(expr, AnyOf):
        children = expr.any
    else:
        return 1
    return 1 + max(expr_depth(child) for child in children)


def _validate_depth(expr: PrereqExpr) -> None:
    depth = expr_depth(expr)
    if depth > MAX_DEPTH:
        raise ValueError(
            f"prereq expression nesting depth {depth} exceeds the maximum of {MAX_DEPTH}"
        )


class PrereqExprRoot(RootModel[PrereqExprField]):
    """Wrapper registering the union under one `prereq_expr` generated schema."""


AllOf.model_rebuild()
AnyOf.model_rebuild()
