"""Arbitrage contract: one Mode B row.

Canonical spec: docs/specs/arbitrage.schema.md.
The wire shape of `GET /api/arbitrage`; the list order is server truth
(`transfer/arbitrage.py` owns the ranking), never re-sorted client-side.

Every value here is produced by deterministic code: candidacy is recomputed
with `evaluate_expr` over the evaluation's resolved course set, never parsed
out of findings text, and no LLM touches Mode B anywhere.
"""

from pydantic import BaseModel, Field, field_validator, model_validator

from starmap.contracts.base import FROZEN, reject_control_chars
from starmap.contracts.codes import CourseCode
from starmap.contracts.dedup import find_duplicates
from starmap.contracts.evaluation import Citation


class ArbitrageRow(BaseModel):
    """One ranked row: the CC courses to take, the receiving requirement they
    complete, and the tuition delta; `savings_dollars` is None (never zero)
    when the target publishes no per-unit rate."""

    model_config = FROZEN

    missing_course_codes: list[CourseCode] = Field(min_length=1)
    receiving_course_code: CourseCode | None = None
    receiving_course_title: str | None = Field(default=None, min_length=1, max_length=300)
    receiving_series_name: str | None = Field(default=None, min_length=1, max_length=300)
    units: float = Field(gt=0)
    savings_dollars: float | None = None
    citation: Citation

    @field_validator("receiving_course_title", "receiving_series_name")
    @classmethod
    def _hygiene(cls, value: str | None) -> str | None:
        return None if value is None else reject_control_chars(value)

    @model_validator(mode="after")
    def _check_missing_course_codes_unique(self) -> "ArbitrageRow":
        duplicates = find_duplicates(self.missing_course_codes)
        if duplicates:
            raise ValueError(f"missing_course_codes contains duplicates: {duplicates}")
        return self

    @model_validator(mode="after")
    def _check_exactly_one_receiving_side(self) -> "ArbitrageRow":
        """A row completes one course OR one series, mirroring `Articulation`:
        "what does taking these courses buy" has to have exactly one answer."""
        if (self.receiving_course_code is None) == (self.receiving_series_name is None):
            raise ValueError(
                "arbitrage row needs exactly one of receiving_course_code and "
                f"receiving_series_name, got code={self.receiving_course_code is not None} "
                f"series={self.receiving_series_name is not None}"
            )
        return self

    @model_validator(mode="after")
    def _check_title_rides_with_code(self) -> "ArbitrageRow":
        if self.receiving_course_title is not None and self.receiving_course_code is None:
            raise ValueError(
                f"receiving_course_title {self.receiving_course_title!r} requires a "
                f"receiving_course_code; a series row displays its series name instead"
            )
        return self
