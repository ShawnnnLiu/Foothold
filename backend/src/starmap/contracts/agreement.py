"""Agreement contract: one published ASSIST articulation agreement, plus the
template-asset models that lay a major agreement's courses out into groups.

Canonical spec: docs/specs/agreement.schema.md.
`agreement_id` is derived from `assist_key`, and both key-coherence validators
exist because the key is the citation every finding carries: if the key and
the structured fields could disagree, a finding could cite one agreement while
having been evaluated against another.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from starmap.common.ids import sha256_hex
from starmap.contracts.articulation import (
    AGREEMENT_ID_HASH_LENGTH,
    AGREEMENT_ID_PATTERN,
    AGREEMENT_ID_PREFIX,
    GUID_PATTERN,
    AdvisementText,
    ReceivingCourse,
)
from starmap.contracts.base import FROZEN, reject_control_chars

# Both observed key formats: a Major key carries a GUID tail, a Department key
# an integer tail. `SendingDepartment` keys are the mirror-direction agreements
# and are deliberately excluded (spec).
ASSIST_KEY_PATTERN = r"^[0-9]+/[0-9]+/to/[0-9]+/(Major|Department)/.+$"
YEAR_LABEL_PATTERN = r"^[0-9]{4}-[0-9]{4}$"

AgreementCategory = Literal["major", "dept"]

# Typed by the category Literal so a widened category cannot compile without
# its key segment (widening `category` is an append, per the overview doc).
KEY_SEGMENT_FOR_CATEGORY: dict[AgreementCategory, str] = {
    "major": "Major",
    "dept": "Department",
}


def derive_agreement_id(assist_key: str) -> str:
    """The single derivation; every producer and the validator go through it."""
    return f"{AGREEMENT_ID_PREFIX}{sha256_hex(assist_key)[:AGREEMENT_ID_HASH_LENGTH]}"


def check_consecutive_years(field_name: str, value: str) -> str:
    """The single consecutive-years rule, shared with `evaluation.Citation`.

    `field_name` is passed in rather than hardcoded because two contracts spell
    the field differently (`academic_year_label`, `year_label`) and validator
    messages must name the field they fired on.
    """
    begin, end = (int(part) for part in value.split("-"))
    if end != begin + 1:
        raise ValueError(
            f"{field_name} {value!r} spans non-consecutive years; expected {begin}-{begin + 1}"
        )
    return value


class Agreement(BaseModel):
    model_config = FROZEN

    agreement_id: str = Field(pattern=AGREEMENT_ID_PATTERN)
    assist_key: str = Field(pattern=ASSIST_KEY_PATTERN)
    category: AgreementCategory
    sending_institution_id: int = Field(gt=0)
    receiving_institution_id: int = Field(gt=0)
    academic_year_id: int = Field(gt=0)
    academic_year_label: str = Field(pattern=YEAR_LABEL_PATTERN)
    label: str = Field(min_length=1, max_length=300)
    publish_date: str = Field(min_length=1, max_length=40)

    @field_validator("label", "publish_date")
    @classmethod
    def _hygiene(cls, value: str) -> str:
        return reject_control_chars(value)

    @field_validator("academic_year_label")
    @classmethod
    def _check_years_are_consecutive(cls, value: str) -> str:
        return check_consecutive_years("academic_year_label", value)

    @model_validator(mode="after")
    def _check_id_derivation(self) -> "Agreement":
        expected = derive_agreement_id(self.assist_key)
        if self.agreement_id != expected:
            raise ValueError(
                f"agreement_id {self.agreement_id!r} is not derived from assist_key "
                f"{self.assist_key!r}; expected {expected!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_institutions_differ(self) -> "Agreement":
        if self.sending_institution_id == self.receiving_institution_id:
            raise ValueError(
                f"sending_institution_id and receiving_institution_id are both "
                f"{self.sending_institution_id!r}; an agreement joins two institutions"
            )
        return self

    @model_validator(mode="after")
    def _check_key_category_coherence(self) -> "Agreement":
        expected = KEY_SEGMENT_FOR_CATEGORY[self.category]
        actual = self.assist_key.split("/")[4]
        if actual != expected:
            raise ValueError(
                f"assist_key {self.assist_key!r} carries segment {actual!r} but category "
                f"{self.category!r} requires {expected!r}"
            )
        return self

    @model_validator(mode="after")
    def _check_key_ids_coherence(self) -> "Agreement":
        segments = self.assist_key.split("/")
        expected = {
            "academic_year_id": (self.academic_year_id, int(segments[0])),
            "sending_institution_id": (self.sending_institution_id, int(segments[1])),
            "receiving_institution_id": (self.receiving_institution_id, int(segments[3])),
        }
        for field, (declared, in_key) in expected.items():
            if declared != in_key:
                raise ValueError(
                    f"assist_key {self.assist_key!r} carries {field} {in_key!r} "
                    f"but the field says {declared!r}"
                )
        return self


class TemplateCell(BaseModel):
    """One receiving course in a major agreement's requirement template.

    `cell_id` is the join key to `Articulation.template_cell_id`; a cell no
    articulation points at means "no articulation published for this cell",
    which must render as unmet rather than vanish.
    """

    model_config = FROZEN

    cell_id: str = Field(pattern=GUID_PATTERN)
    course: ReceivingCourse


class TemplateSection(BaseModel):
    model_config = FROZEN

    position: int = Field(ge=0)
    cells: list[TemplateCell] = Field(min_length=1)


class RequirementGroupAsset(BaseModel):
    """A normalized ASSIST `RequirementGroup` asset (major agreements only).

    The normalizer has already collapsed rows into their section's cells and
    resolved `instruction` into `conjunction`; this contract never sees a row
    or an instruction object.
    """

    model_config = FROZEN

    group_id: str = Field(pattern=GUID_PATTERN)
    position: int = Field(ge=0)
    conjunction: Literal["And", "Or"]
    sections: list[TemplateSection] = Field(min_length=1)
    advisements: list[AdvisementText] = Field(default_factory=list)
