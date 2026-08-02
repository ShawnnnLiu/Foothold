"""The ASSIST corridor: which agreements the build pulls, and from where.

This module owns every ASSIST-specific url and the walk that enumerates the
corridor; `fetch.py` owns only "get me this url politely and cache it". Doc 02
lists the url builders under `fetch.py`, but the walk needs both the builders
and the fetcher, so keeping the builders here is what makes the dependency
one-way (`corridor` -> `fetch`) instead of circular.

The walk is the fetch STAGE: it decides the scope, warms the cache with every
agreement payload, and returns a `CorridorScope` describing what it saw.
It parses only enough of each list payload to steer itself; turning agreement
payloads into contracts is `normalize.py`, which reads the same cache later.

Fault isolation, locked:

- A failed agreement payload fetch is recorded as a `FetchFailure` on its pair
  and the walk continues; one bad agreement never breaks the build.
- A failed categories or reports-list fetch ends that pair with a
  `scope_error` and the walk continues to the next pair.
- A `session_bootstrap_failed` is NOT isolated. It is a global condition, and
  swallowing it per pair would silently burn hundreds of requests, so it
  propagates out of the walk.
"""

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from starmap.assist.errors import AssistFetchError
from starmap.assist.fetch import AssistFetcher
from starmap.contracts.reason_codes import AssistBuildCode

BASE_URL = "https://www.assist.org"
ROOT_URL = f"{BASE_URL}/"
TARGET_IDS = (7, 39, 117, 120)  # UCSD, SJSU, UCLA, UCI (plan corridor, ids from institutions.json)
DEMO_SENDING_ID = 113  # De Anza
DEMO_RECEIVING_ID = 7  # UCSD
PINNED_MAJOR_KEYWORDS = ("computer science", "economics", "psychology", "biology", "business")
PREFERRED_YEAR_ID = 76  # 2025-2026, latest published (spike doc)
YEAR_FALLBACK_DEPTH = 2  # try 76, then 75, then 74 per pair

Category = Literal["major", "dept"]


# --- urls -------------------------------------------------------------------


def academic_years_url() -> str:
    return f"{BASE_URL}/api/AcademicYears"


def institutions_url() -> str:
    return f"{BASE_URL}/api/institutions"


def categories_url(receiving_id: int, sending_id: int, year_id: int) -> str:
    return (
        f"{BASE_URL}/api/agreements/categories"
        f"?receivingInstitutionId={receiving_id}"
        f"&sendingInstitutionId={sending_id}"
        f"&academicYearId={year_id}"
    )


def agreements_url(receiving_id: int, sending_id: int, year_id: int, category: Category) -> str:
    return (
        f"{BASE_URL}/api/agreements"
        f"?receivingInstitutionId={receiving_id}"
        f"&sendingInstitutionId={sending_id}"
        f"&academicYearId={year_id}"
        f"&categoryCode={category}"
    )


def agreement_url(key: str) -> str:
    """Agreement keys contain `/`, so the whole key is percent-encoded."""
    return f"{BASE_URL}/api/articulation/Agreements?Key={quote(key, safe='')}"


# --- what a walk produces ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class AgreementRef:
    """One agreement the corridor wants, named exactly as `normalize` needs it."""

    assist_key: str
    category: Category
    label: str
    sending_id: int
    receiving_id: int
    year_id: int


@dataclass(frozen=True, slots=True)
class FetchFailure:
    assist_key: str
    reason_code: AssistBuildCode
    detail: str


@dataclass(frozen=True, slots=True)
class PairScope:
    """One (community college, target) pair. `year_id is None` means no published year."""

    sending_id: int
    receiving_id: int
    year_id: int | None
    major_reports: int = 0
    major_selected: int = 0
    dept_reports: int = 0
    agreements: tuple[AgreementRef, ...] = ()
    fetch_failures: tuple[FetchFailure, ...] = ()
    scope_error: str | None = None


@dataclass(frozen=True, slots=True)
class CorridorScope:
    targets: tuple[int, ...]
    sending_count: int
    preferred_year_id: int
    pairs: tuple[PairScope, ...] = ()


# --- payload readers --------------------------------------------------------


def _as_list(value: object, *, what: str) -> list[object]:
    if not isinstance(value, list):
        raise AssistFetchError(
            f"ASSIST {what} payload was not a list",
            reason_code=AssistBuildCode.AGREEMENT_FETCH_FAILED,
        )
    return value


def _entries(value: object, *, what: str) -> Iterator[dict[str, object]]:
    for entry in _as_list(value, what=what):
        if not isinstance(entry, dict):
            raise AssistFetchError(
                f"ASSIST {what} payload held a non-object entry",
                reason_code=AssistBuildCode.AGREEMENT_FETCH_FAILED,
            )
        yield entry


def community_college_ids(institutions: object) -> tuple[int, ...]:
    """The authoritative sending-side filter is `isCommunityCollege` (spike implication 5)."""
    ids: list[int] = []
    for entry in _entries(institutions, what="institutions"):
        identifier = entry.get("id")
        if entry.get("isCommunityCollege") is True and isinstance(identifier, int):
            ids.append(identifier)
    return tuple(sorted(ids))


def major_category_has_reports(categories: object) -> bool:
    for entry in _entries(categories, what="categories"):
        if entry.get("code") == "major":
            return entry.get("hasReports") is True
    return False


def _report_refs(
    payload: object,
    *,
    category: Category,
    sending_id: int,
    receiving_id: int,
    year_id: int,
) -> tuple[AgreementRef, ...]:
    """`{reports: [...], allReports: [...]}`; `allReports` is a rollup we never fetch."""
    if not isinstance(payload, dict):
        raise AssistFetchError(
            f"ASSIST {category} reports payload was not an object",
            reason_code=AssistBuildCode.AGREEMENT_FETCH_FAILED,
        )
    refs = []
    for entry in _entries(payload.get("reports"), what=f"{category} reports"):
        key = entry.get("key")
        label = entry.get("label")
        if not isinstance(key, str) or not isinstance(label, str):
            raise AssistFetchError(
                f"ASSIST {category} report entry had no string key and label",
                reason_code=AssistBuildCode.AGREEMENT_FETCH_FAILED,
            )
        refs.append(
            AgreementRef(
                assist_key=key,
                category=category,
                label=label,
                sending_id=sending_id,
                receiving_id=receiving_id,
                year_id=year_id,
            )
        )
    return tuple(refs)


def matches_pinned_keyword(label: str) -> bool:
    folded = label.casefold()
    return any(keyword in folded for keyword in PINNED_MAJOR_KEYWORDS)


# --- the walk ---------------------------------------------------------------


def walk_corridor(
    fetcher: AssistFetcher, *, only_pair: tuple[int, int] | None = None
) -> CorridorScope:
    """Fetch every agreement payload the corridor needs and describe what was seen."""
    fetcher.fetch_json(academic_years_url())  # cached for the store's `academic_years` table
    sending_ids = community_college_ids(fetcher.fetch_json(institutions_url()))
    targets = tuple(sorted(TARGET_IDS))
    pairs = tuple(
        _walk_pair(fetcher, sending_id, receiving_id)
        for sending_id, receiving_id in _pairs(sending_ids, targets, only_pair)
    )
    return CorridorScope(
        targets=targets,
        sending_count=len(sending_ids),
        preferred_year_id=PREFERRED_YEAR_ID,
        pairs=pairs,
    )


def _pairs(
    sending_ids: Iterable[int], targets: Iterable[int], only_pair: tuple[int, int] | None
) -> Iterator[tuple[int, int]]:
    """(cc id asc, target id asc), the locked walk order."""
    for sending_id in sending_ids:
        for receiving_id in targets:
            if only_pair is None or (sending_id, receiving_id) == only_pair:
                yield sending_id, receiving_id


def _isolate(error: AssistFetchError) -> str:
    """Per-pair isolation. A session failure is global and is re-raised."""
    if error.assist_reason_code is AssistBuildCode.SESSION_BOOTSTRAP_FAILED:
        raise error
    return error.message


def _walk_pair(fetcher: AssistFetcher, sending_id: int, receiving_id: int) -> PairScope:
    try:
        year_id = _resolve_year(fetcher, sending_id, receiving_id)
    except AssistFetchError as error:
        return PairScope(sending_id, receiving_id, None, scope_error=_isolate(error))
    if year_id is None:
        return PairScope(sending_id, receiving_id, None)

    is_demo = (sending_id, receiving_id) == (DEMO_SENDING_ID, DEMO_RECEIVING_ID)
    try:
        majors = _reports(fetcher, sending_id, receiving_id, year_id, "major")
    except AssistFetchError as error:
        return PairScope(sending_id, receiving_id, year_id, scope_error=_isolate(error))
    selected = majors if is_demo else tuple(r for r in majors if matches_pinned_keyword(r.label))

    # Department depth beyond the demo pair is cuttable major-depth per the plan;
    # the sending-CC breadth never is.
    depts: tuple[AgreementRef, ...] = ()
    scope_error: str | None = None
    if is_demo:
        try:
            depts = _reports(fetcher, sending_id, receiving_id, year_id, "dept")
        except AssistFetchError as error:
            scope_error = _isolate(error)

    agreements: list[AgreementRef] = []
    failures: list[FetchFailure] = []
    for ref in (*selected, *depts):
        try:
            fetcher.fetch_json(agreement_url(ref.assist_key))
        except AssistFetchError as error:
            failures.append(
                FetchFailure(
                    assist_key=ref.assist_key,
                    reason_code=AssistBuildCode.AGREEMENT_FETCH_FAILED,
                    detail=_isolate(error),
                )
            )
            continue
        agreements.append(ref)

    return PairScope(
        sending_id=sending_id,
        receiving_id=receiving_id,
        year_id=year_id,
        major_reports=len(majors),
        major_selected=len(selected),
        dept_reports=len(depts),
        agreements=tuple(agreements),
        fetch_failures=tuple(failures),
        scope_error=scope_error,
    )


def _resolve_year(fetcher: AssistFetcher, sending_id: int, receiving_id: int) -> int | None:
    """Latest published year is discovered per pair, never assumed (spike implication 6)."""
    for offset in range(YEAR_FALLBACK_DEPTH + 1):
        year_id = PREFERRED_YEAR_ID - offset
        categories = fetcher.fetch_json(categories_url(receiving_id, sending_id, year_id))
        if major_category_has_reports(categories):
            return year_id
    return None


def _reports(
    fetcher: AssistFetcher,
    sending_id: int,
    receiving_id: int,
    year_id: int,
    category: Category,
) -> tuple[AgreementRef, ...]:
    payload = fetcher.fetch_json(agreements_url(receiving_id, sending_id, year_id, category))
    return _report_refs(
        payload,
        category=category,
        sending_id=sending_id,
        receiving_id=receiving_id,
        year_id=year_id,
    )
