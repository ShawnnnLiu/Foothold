"""Course-code normalization.

The regex is the increment 1 spike's final decision (`docs/notes/day1_spikes.md`,
"Course-code regex: final"): the proposed default needed no widening.
"""

import re
from typing import Annotated

from pydantic import AfterValidator

COURSE_CODE_RE = re.compile(r"^[A-Z]{2,4} [A-Z]{1,2}[0-9]{4}$")


def normalize_course_code(raw: str) -> str:
    """Uppercase, collapse internal whitespace to one space, strip.

    Raises `ValueError` naming the input if the result fails `COURSE_CODE_RE`.
    """
    normalized = " ".join(raw.upper().split())
    if not COURSE_CODE_RE.fullmatch(normalized):
        raise ValueError(f"invalid course code: {raw!r}")
    return normalized


CourseCode = Annotated[str, AfterValidator(normalize_course_code)]
