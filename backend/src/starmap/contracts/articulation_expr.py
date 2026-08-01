"""Articulation sending-side expression tree: recursive discriminated union.

Canonical spec: docs/specs/articulation_expr.schema.md.
Members are structurally discriminated by their distinct required keys
(`all`, `any`, `course`, `note`); `parse_articulation_expr` owns the dispatch.
Consumers type expression fields as the union with a `BeforeValidator`
calling `parse_articulation_expr`.

Generalized from the pre-pivot `prereq_expr` contract on 2026-07-31: same
structure, depth rule, and dispatch, minus `CourseLeaf.equivalent_ok` and with
the note cap widened to 2000 (rationale in the spec).
"""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, RootModel, field_validator, model_validator

from starmap.contracts.base import FROZEN, reject_control_chars
from starmap.contracts.codes import CourseCode

MAX_DEPTH = 3


def parse_articulation_expr(data: object) -> object:
    """Dispatch a mapping to its union member by discriminating key."""
    if isinstance(data, AllOf | AnyOf | CourseLeaf | NoteLeaf):
        return data
    if not isinstance(data, dict):
        raise ValueError(f"articulation expression must be a mapping, got {type(data).__name__}")
    if "all" in data:
        return AllOf.model_validate(data)
    if "any" in data:
        return AnyOf.model_validate(data)
    if "course" in data:
        return CourseLeaf.model_validate(data)
    if "note" in data:
        return NoteLeaf.model_validate(data)
    raise ValueError(
        "articulation expression must contain one of the keys 'all', 'any', 'course', 'note'"
    )


class CourseLeaf(BaseModel):
    model_config = FROZEN

    course: CourseCode


class NoteLeaf(BaseModel):
    model_config = FROZEN

    note: str = Field(min_length=1, max_length=2000)

    @field_validator("note")
    @classmethod
    def _hygiene(cls, value: str) -> str:
        return reject_control_chars(value)


class AllOf(BaseModel):
    model_config = FROZEN

    all: "list[ArticulationExprField]" = Field(min_length=1)

    @model_validator(mode="after")
    def _check_depth(self) -> "AllOf":
        _validate_depth(self)
        return self


class AnyOf(BaseModel):
    model_config = FROZEN

    any: "list[ArticulationExprField]" = Field(min_length=1)

    @model_validator(mode="after")
    def _check_depth(self) -> "AnyOf":
        _validate_depth(self)
        return self


ArticulationExpr = AllOf | AnyOf | CourseLeaf | NoteLeaf
ArticulationExprField = Annotated[ArticulationExpr, BeforeValidator(parse_articulation_expr)]


def expr_depth(expr: ArticulationExpr) -> int:
    """Nesting depth: a bare leaf is depth 1 and each group level adds 1."""
    if isinstance(expr, AllOf):
        children: list[ArticulationExpr] = expr.all
    elif isinstance(expr, AnyOf):
        children = expr.any
    else:
        return 1
    return 1 + max(expr_depth(child) for child in children)


def _validate_depth(expr: ArticulationExpr) -> None:
    depth = expr_depth(expr)
    if depth > MAX_DEPTH:
        raise ValueError(
            f"articulation expression nesting depth {depth} exceeds the maximum of {MAX_DEPTH}"
        )


class ArticulationExprRoot(RootModel[ArticulationExprField]):
    """Wrapper registering the union under one `articulation_expr` generated schema."""


AllOf.model_rebuild()
AnyOf.model_rebuild()
