import pytest
from pydantic import ValidationError

from starmap.contracts.llm_call_log import LlmCallLogRecord, LlmNode
from tests.support.fixtures import FixtureCase, fixture_ids, iter_fixtures

VALID = list(iter_fixtures("valid", "llm_call_log"))
INVALID = list(iter_fixtures("invalid", "llm_call_log"))

SPEC_NODES = {"transcript_parser", "petition_writer"}


@pytest.mark.parametrize("case", VALID, ids=fixture_ids)
def test_valid_fixtures_parse(case: FixtureCase) -> None:
    record = LlmCallLogRecord.model_validate(case.payload)
    assert record.created_at.utcoffset() is not None


@pytest.mark.parametrize("case", INVALID, ids=fixture_ids)
def test_invalid_fixtures_raise_with_expected_substrings(case: FixtureCase) -> None:
    with pytest.raises(ValidationError) as excinfo:
        LlmCallLogRecord.model_validate(case.payload)
    message = str(excinfo.value)
    assert case.expected_substrings is not None
    for substring in case.expected_substrings:
        assert substring in message, f"{substring!r} not in error for {case.path.name}"


def test_model_is_frozen() -> None:
    record = LlmCallLogRecord.model_validate(VALID[0].payload)
    with pytest.raises(ValidationError):
        record.run_id = "mutated"


def test_unknown_field_rejected() -> None:
    payload = dict(VALID[0].payload) | {"unexpected_field": 1}
    with pytest.raises(ValidationError, match="unexpected_field"):
        LlmCallLogRecord.model_validate(payload)


def test_raw_content_fields_are_structurally_impossible() -> None:
    """`extra="forbid"` is the guarantee, not just hygiene."""
    for field in ("system", "user_prompt", "raw_text", "response_text"):
        payload = dict(VALID[0].payload) | {field: "leaked"}
        with pytest.raises(ValidationError, match=field):
            LlmCallLogRecord.model_validate(payload)


def test_node_enum_matches_the_spec_table() -> None:
    assert {member.value for member in LlmNode} == SPEC_NODES
