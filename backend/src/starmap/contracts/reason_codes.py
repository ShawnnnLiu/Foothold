"""Typed reason-code families.

Canonical spec: docs/specs/reason_codes.schema.md.
Values are snake_case and families are append-only forever; adding a member
updates the spec in the same commit.

One-time exception, 2026-07-31: the pivot removed `PrereqExtractionCode`,
`BuildCode`, and `CorpusCode`. None ever shipped a producer, so no artifact or
log row carries their values and nothing can dangle. The rationale is recorded
in the spec; append-only binds normally from here.
"""

from enum import StrEnum


class LlmReasonCode(StrEnum):
    AUTH_FAILED = "auth_failed"
    RATE_LIMITED = "rate_limited"
    CALL_FAILED = "call_failed"
    RETRY_LIMIT_EXCEEDED = "retry_limit_exceeded"
    REFUSAL = "refusal"
    TRUNCATED = "truncated"
    MALFORMED_OUTPUT = "malformed_output"
    SCHEMA_REJECTED = "schema_rejected"
    REPAIR_LIMIT_EXCEEDED = "repair_limit_exceeded"


class EvaluationFindingCode(StrEnum):
    TRANSFERS_CLEAN = "transfers_clean"
    ADVISEMENT_NOTE = "advisement_note"
    PARTIAL_SERIES = "partial_series"
    FUZZY_MATCH = "fuzzy_match"
    STALE_YEAR = "stale_year"
    NO_ARTICULATION = "no_articulation"
    STILL_OWED = "still_owed"
    DOUBLE_COUNT_RISK = "double_count_risk"
    UNRESOLVED = "unresolved"


class TriageBucket(StrEnum):
    TRANSFERS_CLEAN = "transfers_clean"
    AT_RISK = "at_risk"
    NO_ARTICULATION = "no_articulation"
    STILL_OWED = "still_owed"


BUCKET_FOR_CODE: dict[EvaluationFindingCode, TriageBucket] = {
    EvaluationFindingCode.TRANSFERS_CLEAN: TriageBucket.TRANSFERS_CLEAN,
    EvaluationFindingCode.ADVISEMENT_NOTE: TriageBucket.AT_RISK,
    EvaluationFindingCode.PARTIAL_SERIES: TriageBucket.AT_RISK,
    EvaluationFindingCode.FUZZY_MATCH: TriageBucket.AT_RISK,
    EvaluationFindingCode.STALE_YEAR: TriageBucket.AT_RISK,
    EvaluationFindingCode.DOUBLE_COUNT_RISK: TriageBucket.AT_RISK,
    EvaluationFindingCode.UNRESOLVED: TriageBucket.AT_RISK,
    EvaluationFindingCode.NO_ARTICULATION: TriageBucket.NO_ARTICULATION,
    EvaluationFindingCode.STILL_OWED: TriageBucket.STILL_OWED,
}


class AssistBuildCode(StrEnum):
    SESSION_BOOTSTRAP_FAILED = "session_bootstrap_failed"
    AGREEMENT_FETCH_FAILED = "agreement_fetch_failed"
    ENVELOPE_INVALID = "envelope_invalid"
    FIELD_DECODE_FAILED = "field_decode_failed"
    ARTICULATION_TYPE_UNSUPPORTED = "articulation_type_unsupported"
    COURSE_CODE_UNPARSEABLE = "course_code_unparseable"
    MIXED_GROUP_CONJUNCTION = "mixed_group_conjunction"
    ADVISEMENT_SHAPE_UNKNOWN = "advisement_shape_unknown"
    TEMPLATE_SHAPE_UNSUPPORTED = "template_shape_unsupported"
    INSTITUTION_KIND_UNKNOWN = "institution_kind_unknown"
    COURSE_PROJECTION_CONFLICT = "course_projection_conflict"


class RetrievalCode(StrEnum):
    FTS5_UNAVAILABLE = "fts5_unavailable"
    INSTITUTION_NOT_INDEXED = "institution_not_indexed"
