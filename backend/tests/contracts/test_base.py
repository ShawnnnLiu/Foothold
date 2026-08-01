import pytest
from pydantic import ValidationError

from starmap.contracts.base import rebuild, reject_control_chars
from starmap.contracts.offering import Offering

OFFERING = Offering.model_validate(
    {"course_code": "COMS W1002", "term": "fall", "year": 2026, "instructors": ["Ada Lovelace"]}
)


def test_rebuild_returns_updated_instance() -> None:
    updated = rebuild(OFFERING, year=2027)
    assert updated.year == 2027
    assert updated.course_code == OFFERING.course_code
    assert OFFERING.year == 2026


def test_rebuild_reruns_model_validators() -> None:
    with pytest.raises(ValidationError, match="case-insensitive duplicates"):
        rebuild(OFFERING, instructors=["Ada Lovelace", "ada lovelace"])


def test_rebuild_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="bogus"):
        rebuild(OFFERING, bogus=1)


def test_reject_control_chars_allows_clean_text() -> None:
    text = "line one\nline two\r\ttabbed"
    assert reject_control_chars(text) == text


def test_reject_control_chars_names_the_codepoint() -> None:
    with pytest.raises(ValueError, match=r"U\+0000"):
        reject_control_chars("bad\x00text")
