"""The fixed-threshold course resolver over a built `CourseIndex`.

Its result vocabulary is exactly the transcript-gate vocabulary (`exact` /
`fuzzy_match` / `unresolved`), so the Week 2 validator consumes it without
translation. It is a total function of its text inputs: garbage in means
`unresolved` out, never a raise.
"""

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal, TypeGuard

from starmap.contracts.codes import normalize_course_code
from starmap.contracts.dedup import casefold_key
from starmap.retrieval.index import CourseIndex, SearchHit

# Locked in implementation plan doc 04; changing either is a spec change, not
# a tuning knob.
FUZZY_ACCEPT_RATIO = 0.6
FUZZY_CANDIDATES_K = 5


@dataclass(frozen=True, slots=True)
class Resolution:
    status: Literal["exact", "fuzzy_match", "unresolved"]
    course_code: str | None
    title: str | None
    units_min: float | None
    units_max: float | None
    ratio: float | None


_UNRESOLVED = Resolution(
    status="unresolved", course_code=None, title=None, units_min=None, units_max=None, ratio=None
)


def _present(value: str | None) -> TypeGuard[str]:
    return value is not None and value.strip() != ""


def _hit_ratio(query_text: str, hit: SearchHit) -> float:
    matcher = SequenceMatcher(
        None, casefold_key(query_text), casefold_key(f"{hit.course_code} {hit.title}")
    )
    return matcher.ratio()


def resolve_course(
    index: CourseIndex, institution_id: int, *, code: str | None, title: str | None
) -> Resolution:
    if not _present(code) and not _present(title):
        return _UNRESOLVED

    # Exact gate: tolerant input, strict store. A code that fails
    # normalization falls through to the fuzzy gate rather than raising.
    if _present(code):
        try:
            normalized = normalize_course_code(code)
        except ValueError:
            normalized = None
        if normalized is not None:
            row = index.lookup(institution_id, normalized)
            if row is not None:
                return Resolution(
                    status="exact",
                    course_code=row.course_code,
                    title=row.title,
                    units_min=row.units_min,
                    units_max=row.units_max,
                    ratio=None,
                )

    query_text = " ".join(part for part in (code, title) if _present(part))
    hits = index.search(institution_id, query_text, k=FUZZY_CANDIDATES_K)
    if not hits:
        return _UNRESOLVED

    scored = [(_hit_ratio(query_text, hit), hit) for hit in hits]
    best_ratio, best = min(scored, key=lambda pair: (-pair[0], -pair[1].score, pair[1].course_code))
    if best_ratio >= FUZZY_ACCEPT_RATIO:
        return Resolution(
            status="fuzzy_match",
            course_code=best.course_code,
            title=best.title,
            units_min=best.units_min,
            units_max=best.units_max,
            ratio=best_ratio,
        )
    return Resolution(
        status="unresolved",
        course_code=None,
        title=None,
        units_min=None,
        units_max=None,
        ratio=best_ratio,
    )
