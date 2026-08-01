import pytest

from starmap.contracts.codes import COURSE_CODE_RE, normalize_course_code

SPIKE_OBSERVED_SHAPES = ["MPP UN1401", "CBMF W4761", "COMS E0001", "AHMM UN3320", "CLEN GU4122"]


@pytest.mark.parametrize("code", SPIKE_OBSERVED_SHAPES)
def test_observed_bulletin_shapes_pass(code: str) -> None:
    assert normalize_course_code(code) == code
    assert COURSE_CODE_RE.fullmatch(code)


def test_normalization_uppercases_and_collapses_whitespace() -> None:
    assert normalize_course_code("  coms   w4701 ") == "COMS W4701"


@pytest.mark.parametrize(
    "raw",
    ["COMS 3134", "C W1234", "COMSX W1234", "COMS ABC1234", "COMS W123", "COMS W12345", ""],
)
def test_invalid_codes_raise_naming_the_input(raw: str) -> None:
    with pytest.raises(ValueError, match="invalid course code"):
        normalize_course_code(raw)
