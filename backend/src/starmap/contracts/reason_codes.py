"""Typed reason-code families.

Canonical spec: docs/specs/reason_codes.schema.md.
Values are snake_case and families are append-only forever; adding a member
updates the spec in the same commit. Week 2 adds the pathway violation
family to this module.
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


class PrereqExtractionCode(StrEnum):
    UNKNOWN_COURSE_LEAF = "unknown_course_leaf"
    UNACCOUNTED_LINKED_CODE = "unaccounted_linked_code"
    EXPR_TOO_DEEP = "expr_too_deep"


class BuildCode(StrEnum):
    DEPT_FETCH_FAILED = "dept_fetch_failed"
    DEPT_PARSE_FAILED = "dept_parse_failed"
    DEPT_EXCLUDED = "dept_excluded"


class CorpusCode(StrEnum):
    CONTENT_HASH_MISMATCH = "content_hash_mismatch"
    DOCUMENT_CONFLICT = "document_conflict"
    UNKNOWN_DOCUMENT = "unknown_document"
    EMPTY_SNAPSHOT = "empty_snapshot"
    FTS5_UNAVAILABLE = "fts5_unavailable"
    SNAPSHOT_NOT_INDEXED = "snapshot_not_indexed"
