import pytest
from pydantic import ValidationError

from starmap.contracts.articulation_expr import AllOf
from starmap.contracts.base import rebuild, reject_control_chars

# The rebuild harness needs a frozen model carrying a real model validator, so
# that "rebuild re-runs every invariant" is proven rather than asserted.
# `AllOf` supplies one: the nesting-depth check.
GROUP = AllOf.model_validate({"all": [{"course": "MATH 1A"}, {"course": "MATH 1B"}]})


def test_rebuild_returns_updated_instance() -> None:
    updated = rebuild(GROUP, all=[{"course": "MATH 1AH"}])
    assert updated.model_dump(mode="json") == {"all": [{"course": "MATH 1AH"}]}
    assert GROUP.model_dump(mode="json") == {"all": [{"course": "MATH 1A"}, {"course": "MATH 1B"}]}


def test_rebuild_reruns_model_validators() -> None:
    too_deep = [{"any": [{"all": [{"any": [{"course": "MATH 1A"}]}]}]}]
    with pytest.raises(ValidationError, match="nesting depth 4 exceeds the maximum of 3"):
        rebuild(GROUP, all=too_deep)


def test_rebuild_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="bogus"):
        rebuild(GROUP, bogus=1)


def test_reject_control_chars_allows_clean_text() -> None:
    text = "line one\nline two\r\ttabbed"
    assert reject_control_chars(text) == text


def test_reject_control_chars_names_the_codepoint() -> None:
    with pytest.raises(ValueError, match=r"U\+0000"):
        reject_control_chars("bad\x00text")
