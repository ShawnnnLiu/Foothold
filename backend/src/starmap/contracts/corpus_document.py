"""Corpus document registry-metadata contract.

Canonical spec: docs/specs/corpus_document.schema.md.
Document text is deliberately not a field; text lives in the registry
beside the record.
"""

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from starmap.common.ids import sha256_hex
from starmap.contracts.base import FROZEN


class CorpusDocument(BaseModel):
    model_config = FROZEN

    doc_id: str = Field(pattern=r"^doc_[0-9a-f]{16}$")
    source_url: str = Field(min_length=1)
    source_type: Literal["bulletin_course", "bulletin_requirement"]
    license_note: str = Field(min_length=1)
    date_collected: date
    source_published_date: date | None = None
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    title: str = Field(min_length=1)

    @model_validator(mode="after")
    def _check_id_derivation(self) -> "CorpusDocument":
        derived = "doc_" + sha256_hex(f"{self.source_url}\n{self.date_collected.isoformat()}")[:16]
        if self.doc_id != derived:
            raise ValueError(
                f"doc_id {self.doc_id!r} does not match the derived id {derived!r} "
                f"for source_url {self.source_url!r} collected {self.date_collected.isoformat()}"
            )
        return self

    @model_validator(mode="after")
    def _check_date_order(self) -> "CorpusDocument":
        if self.source_published_date is not None and (
            self.source_published_date > self.date_collected
        ):
            raise ValueError(
                f"source_published_date {self.source_published_date.isoformat()} is after "
                f"date_collected {self.date_collected.isoformat()}"
            )
        return self
