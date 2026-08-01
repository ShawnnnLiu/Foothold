import re
from enum import StrEnum

import pytest

from starmap.contracts.reason_codes import (
    BuildCode,
    CorpusCode,
    LlmReasonCode,
    PrereqExtractionCode,
)

SPEC_TABLES: dict[type[StrEnum], set[str]] = {
    LlmReasonCode: {
        "auth_failed",
        "rate_limited",
        "call_failed",
        "retry_limit_exceeded",
        "refusal",
        "truncated",
        "malformed_output",
        "schema_rejected",
        "repair_limit_exceeded",
    },
    PrereqExtractionCode: {"unknown_course_leaf", "unaccounted_linked_code", "expr_too_deep"},
    BuildCode: {"dept_fetch_failed", "dept_parse_failed", "dept_excluded"},
    CorpusCode: {
        "content_hash_mismatch",
        "document_conflict",
        "unknown_document",
        "empty_snapshot",
        "fts5_unavailable",
        "snapshot_not_indexed",
    },
}


@pytest.mark.parametrize("family", SPEC_TABLES, ids=lambda family: family.__name__)
def test_family_matches_spec_table(family: type[StrEnum]) -> None:
    assert {member.value for member in family} == SPEC_TABLES[family]


@pytest.mark.parametrize("family", SPEC_TABLES, ids=lambda family: family.__name__)
def test_values_are_snake_case(family: type[StrEnum]) -> None:
    for member in family:
        assert re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", member.value), member
