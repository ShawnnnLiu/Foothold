import re
from enum import StrEnum

import pytest

from starmap.contracts.reason_codes import (
    BUCKET_FOR_CODE,
    AssistBuildCode,
    EvaluationFindingCode,
    LlmReasonCode,
    RetrievalCode,
    TriageBucket,
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
    EvaluationFindingCode: {
        "transfers_clean",
        "advisement_note",
        "partial_series",
        "fuzzy_match",
        "stale_year",
        "no_articulation",
        "still_owed",
        "double_count_risk",
        "unresolved",
    },
    TriageBucket: {"transfers_clean", "at_risk", "no_articulation", "still_owed"},
    AssistBuildCode: {
        "session_bootstrap_failed",
        "agreement_fetch_failed",
        "envelope_invalid",
        "field_decode_failed",
        "articulation_type_unsupported",
        "course_code_unparseable",
        "mixed_group_conjunction",
        "advisement_shape_unknown",
        "template_shape_unsupported",
        "institution_kind_unknown",
        "course_projection_conflict",
    },
    RetrievalCode: {"fts5_unavailable", "institution_not_indexed"},
}

# The normative BUCKET_FOR_CODE table in docs/specs/reason_codes.schema.md,
# transcribed; divergence between spec table and module is a failure.
SPEC_BUCKET_TABLE: dict[str, str] = {
    "transfers_clean": "transfers_clean",
    "advisement_note": "at_risk",
    "partial_series": "at_risk",
    "fuzzy_match": "at_risk",
    "stale_year": "at_risk",
    "double_count_risk": "at_risk",
    "unresolved": "at_risk",
    "no_articulation": "no_articulation",
    "still_owed": "still_owed",
}


@pytest.mark.parametrize("family", SPEC_TABLES, ids=lambda family: family.__name__)
def test_family_matches_spec_table(family: type[StrEnum]) -> None:
    assert {member.value for member in family} == SPEC_TABLES[family]


@pytest.mark.parametrize("family", SPEC_TABLES, ids=lambda family: family.__name__)
def test_values_are_snake_case(family: type[StrEnum]) -> None:
    for member in family:
        assert re.fullmatch(r"[a-z0-9]+(_[a-z0-9]+)*", member.value), member


def test_bucket_mapping_is_total_over_finding_codes() -> None:
    assert set(BUCKET_FOR_CODE) == set(EvaluationFindingCode)


def test_bucket_mapping_matches_the_spec_table() -> None:
    actual = {code.value: bucket.value for code, bucket in BUCKET_FOR_CODE.items()}
    assert actual == SPEC_BUCKET_TABLE


def test_unresolved_is_amber_not_red() -> None:
    """An unresolved input is a student-fixable problem, not a claim about the agreement."""
    assert BUCKET_FOR_CODE[EvaluationFindingCode.UNRESOLVED] == TriageBucket.AT_RISK
