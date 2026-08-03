import re

import pytest

from starmap.contracts.codes import (
    COURSE_CODE_RE,
    COURSE_NUMBER_PATTERN,
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


# Shapes the pre-S9c regex rejected, found when the first full corridor build
# excluded 1,624 articulations across 150 codes. Each entry is a real code the
# corridor publishes, with the college that publishes it.
CORRIDOR_OBSERVED_SHAPES = [
    "BUS1 20",  # San Jose State: digit inside the prefix token
    "BUS2 90",
    "BUS4 91L",
    "IN4MATX 43",  # UC Irvine informatics
    "MATH 151 F",  # Fullerton: trailing campus-suffix token
    "CSCI 133 C",  # Cypress
    "CHEM 211 AC",  # two-letter suffix
    "STAT C1000 H",  # letter-prefixed number plus suffix token
    "MATH -04A",  # leading hyphen on the number
    "MATH -08",
    "BIO 2.1",  # decimal number
    "CS 17.11",
    "MATH 103E+",  # plus suffix
    "CIST 004B1",  # letter then digit in the trailing group
    "MATH 120-S",  # embedded hyphen
]

# Shapes the S9c regex still rejected, found by the fifteen-campus S9d corridor.
S9D_OBSERVED_SHAPES = [
    "ENGL 1AMCH",  # English 1A Multicultural Honors: a 4-character trailing group
    "FAM &CS 021",  # Family & Consumer Sciences: a continuation prefix token opening with `&`
    "PEAC TEN1",  # activity courses numbered by mnemonic: tennis, yoga, ballet
    "PEAC YOG1",
    "DANC BAL1",
]


@pytest.mark.parametrize(
    "code", [*SPIKE_OBSERVED_SHAPES, *CORRIDOR_OBSERVED_SHAPES, *S9D_OBSERVED_SHAPES]
)
def test_observed_assist_shapes_pass(code: str) -> None:
    assert normalize_course_code(code) == code
    assert COURSE_CODE_RE.fullmatch(code)


def test_normalization_uppercases_and_collapses_whitespace() -> None:
    assert normalize_course_code("  math   1a ") == "MATH 1A"


def test_course_code_from_parts_joins_and_normalizes() -> None:
    assert course_code_from_parts("STAT", "C1000H") == "STAT C1000H"


@pytest.mark.parametrize(
    "raw",
    [
        "MATH",
        "1A",
        "MATH 12345",  # still rejected: the trailing group cannot start with a digit
        "MATH 1ABCDE",  # 5 trailing letters; 4 became legal in S9d, see below
        "&FAM CS 021",  # only a CONTINUATION prefix token may open with `&`
        "",
        "MATH 1A EXTRA WORD",  # the suffix token is 1-2 letters, not free text
        "MATH 1A B C",
        "2MATH 1A",  # a prefix token still has to START with a letter
    ],
)
def test_invalid_codes_raise_naming_the_input(raw: str) -> None:
    """S9c and S9d widened the regex; these prove it did not become a wildcard.

    `MATH 12345` is the specific case that motivated requiring the number's
    trailing group to start with a non-digit: allowing digits there (needed for
    `CIST 004B1`) would otherwise have let any 5-digit number through.

    The boundary MOVED in S9d and this is the honest record of what that cost.
    `MATH 1ABCD` used to be here and is now legal, because the corridor
    publishes `ENGL 1AMCH` (English 1A, Multicultural Honors) and the two are
    structurally identical - one digit followed by four letters. No length rule
    can admit the real code and reject the invented one, so the trailing group
    grew from 3 characters to 4 and the guard moved out one place, to 5.
    """
    with pytest.raises(ValueError, match="invalid course code"):
        normalize_course_code(raw)


def test_the_number_pattern_admits_an_internal_space_but_never_a_padded_one() -> None:
    """ASSIST publishes `courseNumber: "C1000 "`. The normalizer collapses that
    before validation, so the contract sees `C1000` and the padded form is not
    something a contract has to accept."""
    assert re.fullmatch(COURSE_NUMBER_PATTERN, "C1000 H")
    assert re.fullmatch(COURSE_NUMBER_PATTERN, "151 F")
    assert not re.fullmatch(COURSE_NUMBER_PATTERN, "C1000 ")
    assert not re.fullmatch(COURSE_NUMBER_PATTERN, " C1000")
