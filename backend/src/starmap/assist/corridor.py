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
# The receiving side of the corridor: every UC undergraduate campus plus the
# six largest CSU transfer destinations. Ids verified against the cached
# `/api/institutions` payload in S9d; UCSF is absent because it enrols no
# undergraduates and therefore publishes no articulation agreements.
TARGET_IDS = (
    7,  # UC San Diego
    11,  # Cal Poly San Luis Obispo
    26,  # San Diego State
    39,  # San Jose State
    42,  # CSU Northridge
    46,  # UC Riverside
    79,  # UC Berkeley
    81,  # CSU Long Beach
    89,  # UC Davis
    117,  # UC Los Angeles
    120,  # UC Irvine
    128,  # UC Santa Barbara
    129,  # CSU Fullerton
    132,  # UC Santa Cruz
    144,  # UC Merced
)
DEMO_SENDING_ID = 113  # De Anza
DEMO_RECEIVING_ID = 7  # UCSD
PINNED_MAJOR_KEYWORDS = ("computer science", "economics", "psychology", "biology", "business")

# The key segment of a receiving-side department agreement. Its mirror,
# `SendingDepartment`, is out of scope for v1 (`docs/specs/agreement.schema.md`).
DEPT_KEY_SEGMENT = "Department"

# Optional per-pair cap on the pinned-keyword selection; None means uncapped.
#
# Keyword matching is substring-based, so one pair matches far more majors than
# the pinned set suggests: 32 of De Anza's 168 UCSD major reports match,
# because "business" catches "Business Analytics Minor" and "computer science"
# catches every CSE specialization. S9c capped it at 6 to keep the first live
# fetch inside one evening. S9d removed the cap: a student's major is either in
# the artifact or it is not, and a triage that answers "no articulation" only
# because the build skipped that agreement is worse than a slower build. The
# cap machinery stays so the corridor can be narrowed again without a redesign.
MAX_MAJORS_PER_PAIR: int | None = None
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
    dept_selected: int = 0
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


def select_depts(refs: Iterable[AgreementRef]) -> tuple[AgreementRef, ...]:
    """Receiving-side department agreements only.

    ASSIST publishes each department agreement twice: once owned by the
    receiving institution (`.../Department/<int>`) and once by the sending one
    (`.../SendingDepartment/<int>`). `agreement.schema.md` calls the sending
    direction out of scope for v1 and says the fetcher never requests it, but
    until S9c nothing enforced that, so all 86 of the demo pair's dept reports
    were fetched and the 36 mirror ones then failed `assist_key` validation as
    `envelope_invalid` noise.

    Verified against the S9c capture before this filter landed: the 36 sending
    agreements contribute 120 articulation pairs, every one of which the 50
    receiving agreements already publish, and those publish 329 more besides.
    Filtering here therefore drops duplicates, never transfer rules.
    """
    return tuple(ref for ref in refs if _key_segment(ref.assist_key) == DEPT_KEY_SEGMENT)


def _key_segment(assist_key: str) -> str:
    """The key's fifth segment, which names the agreement's owning side."""
    segments = assist_key.split("/")
    return segments[4] if len(segments) > 4 else ""


def _first_keyword(label: str) -> int:
    """Which pinned keyword owns this label: the earliest one that matches."""
    folded = label.casefold()
    return next(
        (index for index, keyword in enumerate(PINNED_MAJOR_KEYWORDS) if keyword in folded),
        len(PINNED_MAJOR_KEYWORDS),
    )


def select_majors(
    refs: Iterable[AgreementRef], *, limit: int | None = MAX_MAJORS_PER_PAIR
) -> tuple[AgreementRef, ...]:
    """The pinned-keyword majors of one pair, deterministic and optionally capped.

    Round-robin across the keyword families rather than a flat alphabetical
    cut: under a cap, taking the first six labels by name would hand back six
    psychology specializations and no computer science at all, which is not the
    corridor the pinned set describes. Uncapped the round-robin no longer
    changes WHICH agreements are selected, only the order they are fetched in,
    and it is kept so that re-imposing a cap needs one constant and no rethink.
    Within a family the order is by label then key, so the selection is a pure
    function of the reports list.
    """
    families: dict[int, list[AgreementRef]] = {}
    for ref in refs:
        if matches_pinned_keyword(ref.label):
            families.setdefault(_first_keyword(ref.label), []).append(ref)
    for group in families.values():
        group.sort(key=lambda ref: (ref.label, ref.assist_key))

    selected: list[AgreementRef] = []
    for depth in range(max((len(group) for group in families.values()), default=0)):
        for index in sorted(families):
            if limit is not None and len(selected) == limit:
                return tuple(selected)
            group = families[index]
            if depth < len(group):
                selected.append(group[depth])
    return tuple(selected)


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
    selected = majors if is_demo else select_majors(majors)

    # Department depth beyond the demo pair is cuttable major-depth per the plan;
    # the sending-CC breadth never is.
    dept_reports: tuple[AgreementRef, ...] = ()
    depts: tuple[AgreementRef, ...] = ()
    scope_error: str | None = None
    if is_demo:
        try:
            dept_reports = _reports(fetcher, sending_id, receiving_id, year_id, "dept")
            depts = select_depts(dept_reports)
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
        dept_reports=len(dept_reports),
        dept_selected=len(depts),
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
