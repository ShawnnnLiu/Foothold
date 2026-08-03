"""Course-code normalization.

The regex is derived from the ASSIST captures (`docs/notes/assist_spike.md`
and the fixtures in `backend/tests/fixtures/assist/`), which replaced the
pre-pivot Columbia bulletin shape on 2026-07-31: California community college
and UC/CSU codes carry multi-token prefixes and letter-suffixed numbers that
the Columbia regex could not express.

Shape: one to three prefix tokens (letters, then letters/digits plus `&/.-`),
one number token (optional leading `-`, up to 2 leading letters, 1-4 digits, an
optional decimal part, up to 3 trailing letters/digits/`+`/`-`), and an optional
trailing campus-suffix token of 1-2 letters.

The first three of those clauses were widened in S9c. The pre-S9c regex was
written from the De Anza-to-UCSD captures alone, and the first full corridor
build excluded 1,624 articulations (~6%) across 150 distinct codes that are
perfectly ordinary elsewhere in California:

- digits inside a prefix token: `BUS1 20`, `BUS2 90` (San Jose State business
  departments, 1,006 of the exclusions), `IN4MATX 43` (UCI);
- a trailing campus-suffix token: `MATH 151 F` (Fullerton), `CSCI 133 C`
  (Cypress), `CHEM 211 AC`;
- a leading hyphen on the number: `MATH -04A`, `MATH -08`;
- decimals and odd suffixes: `BIO 2.1`, `CS 17.11`, `MATH 103E+`, `MATH 120-S`.

This is deliberately looser than before, which does mean a malformed code is
likelier to pass than to be excluded. The compensating check is the round trip
`course_code == course_code_from_parts(prefix, number)`, enforced by every model
that stores the split pair.
"""

import re
from typing import Annotated

from pydantic import AfterValidator

_PREFIX_TOKEN = r"[A-Z][A-Z0-9&/.\-]{0,9}"
# A CONTINUATION prefix token may open with `&`, which the first one may not:
# "Family & Consumer Sciences" publishes `FAM &CS`, while a leading `&FAM` is
# malformed. Keeping the two tokens distinct buys the real shape without
# admitting the bogus one (S9d).
_PREFIX_CONTINUATION_TOKEN = r"[A-Z&][A-Z0-9&/.\-]{0,9}"
# The trailing group must START with a non-digit, so `MATH 12345` stays invalid
# while `CIST 004B1`, `MATH 103E+`, and `MATH 120-S` do not. Its length grew
# from 3 to 4 in S9d for `ENGL 1AMCH` (Multicultural Honors).
#
# The LEADING letter run grew from 2 to 3 in the same split, for the activity
# courses community colleges number by mnemonic rather than by digit: `PEAC
# TEN1` (tennis), `PEAC YOG1` (yoga), `DANC BAL1` (ballet). A digit is still
# required, so a purely alphabetic number never parses.
_NUMBER_TOKEN = r"-?[A-Z]{0,3}[0-9]{1,4}(?:\.[0-9]{1,2})?(?:[A-Z+\-][A-Z0-9+\-]{0,3})?"
_SUFFIX_TOKEN = r"[A-Z]{1,2}"

COURSE_CODE_RE = re.compile(
    rf"^{_PREFIX_TOKEN}(?: {_PREFIX_CONTINUATION_TOKEN}){{0,2}}"
    rf" {_NUMBER_TOKEN}(?: {_SUFFIX_TOKEN})?$"
)

# The two halves of a code as ASSIST publishes them, shared by every contract
# that stores the split pair beside the derived code: `ReceivingCourse`,
# `CcCourse`, `TargetCourse`. One home keeps three field declarations from
# drifting apart while `course_code_from_parts` keeps joining them.
#
# `COURSE_NUMBER_PATTERN` admits an INTERNAL space, because ASSIST publishes the
# campus suffix as part of the number (`courseNumber: "151 F"`). It never admits
# a leading or trailing one: the normalizer strips and collapses both parts
# before validating, so padded values like `"C1000 "` cannot reach a contract.
COURSE_PREFIX_PATTERN = r"^[A-Z][A-Z0-9&/. \-]{0,15}$"
COURSE_NUMBER_PATTERN = r"^[A-Z0-9.+\-]{1,8}(?: [A-Z]{1,2})?$"
COURSE_NUMBER_MAX_LENGTH = 11  # the pattern's longest match: 8 + space + 2


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
