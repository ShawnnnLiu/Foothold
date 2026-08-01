import pytest

from starmap.contracts.codes import (
    COURSE_CODE_RE,
    course_code_from_parts,
    normalize_course_code,
)

SPIKE_OBSERVED_SHAPES = [
    "MATH 1A",
    "MATH 2AH",
    "STAT C1000H",
    "CIS 22C",
    "CIS 22CH",
    "CSE 15L",
    "MATH 20E",
    "CSE 11",
]


@pytest.mark.parametrize("code", SPIKE_OBSERVED_SHAPES)
def test_observed_assist_shapes_pass(code: str) -> None:
    assert normalize_course_code(code) == code
    assert COURSE_CODE_RE.fullmatch(code)


def test_normalization_uppercases_and_collapses_whitespace() -> None:
    assert normalize_course_code("  math   1a ") == "MATH 1A"


def test_course_code_from_parts_joins_and_normalizes() -> None:
    assert course_code_from_parts("STAT", "C1000H") == "STAT C1000H"


@pytest.mark.parametrize(
    "raw",
    ["MATH", "1A", "MATH 12345", "MATH 1ABCD", ""],
)
def test_invalid_codes_raise_naming_the_input(raw: str) -> None:
    with pytest.raises(ValueError, match="invalid course code"):
        normalize_course_code(raw)
