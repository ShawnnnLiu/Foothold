"""Course-code normalization.

The regex is derived from the ASSIST captures (`docs/notes/assist_spike.md`
and the fixtures in `backend/tests/fixtures/assist/`), which replaced the
pre-pivot Columbia bulletin shape on 2026-07-31: California community college
and UC/CSU codes carry multi-token prefixes and letter-suffixed numbers that
the Columbia regex could not express.

Shape: one to three prefix tokens (letters plus `&/.-`), then one number token
(up to 2 leading letters, 1-4 digits, up to 3 trailing letters).
"""

import re
from typing import Annotated

from pydantic import AfterValidator

COURSE_CODE_RE = re.compile(
    r"^[A-Z][A-Z&/.\-]{0,9}(?: [A-Z][A-Z&/.\-]{0,9}){0,2} [A-Z]{0,2}[0-9]{1,4}[A-Z]{0,3}$"
)


def normalize_course_code(raw: str) -> str:
    """Uppercase, collapse internal whitespace to one space, strip.

    Raises `ValueError` naming the input if the result fails `COURSE_CODE_RE`.
    """
    normalized = " ".join(raw.upper().split())
    if not COURSE_CODE_RE.fullmatch(normalized):
        raise ValueError(f"invalid course code: {raw!r}")
    return normalized


def course_code_from_parts(prefix: str, number: str) -> str:
    """The single derivation from a payload's split prefix/number pair.

    Every contract validator and normalizer that reconstructs a code from an
    ASSIST payload goes through here, so the derivation cannot drift between
    call sites.
    """
    return normalize_course_code(f"{prefix} {number}")


CourseCode = Annotated[str, AfterValidator(normalize_course_code)]
