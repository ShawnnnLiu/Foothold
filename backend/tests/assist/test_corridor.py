"""The corridor: url builders, the payload readers, and the walk.

The walk runs against the seven captured ASSIST fixtures through the scripted
transport, so the demo pair's real shape (168 major reports, 86 department
reports, year 76) is what the assertions pin. No network, no live payloads.
"""

import json
from pathlib import Path

import pytest

from starmap.assist.corridor import (
    DEMO_RECEIVING_ID,
    DEMO_SENDING_ID,
    PREFERRED_YEAR_ID,
    ROOT_URL,
    TARGET_IDS,
    YEAR_FALLBACK_DEPTH,
    AgreementRef,
    academic_years_url,
    agreement_url,
    agreements_url,
    categories_url,
    community_college_ids,
    institutions_url,
    major_category_has_reports,
    matches_pinned_keyword,
    walk_corridor,
)
from starmap.assist.errors import AssistFetchError
from starmap.contracts.reason_codes import AssistBuildCode
from tests.assist.conftest import Harness, Script, Scripted
from tests.support.http import FakeHttpTransport, json_ok, raw, status

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "assist"
DEMO_PAIR = (DEMO_SENDING_ID, DEMO_RECEIVING_ID)
OTHER_CC = 114
AGREEMENT_BODY = {"isSuccessful": True, "result": {}}


def fixture(name: str) -> object:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def reports_of(payload: object) -> list[dict[str, str]]:
    assert isinstance(payload, dict)
    entries = payload["reports"]
    assert isinstance(entries, list)
    return entries


def categories(*, major: bool, dept: bool = True) -> object:
    return [
        {"code": "major", "hasReports": major},
        {"code": "dept", "hasReports": dept},
    ]


def report_list(labels: list[str], *, prefix: str) -> dict[str, object]:
    return {
        "reports": [{"label": label, "key": f"{prefix}/{i}"} for i, label in enumerate(labels)],
        "allReports": [],
    }


# --- urls -------------------------------------------------------------------


def test_the_url_builders_are_exact() -> None:
    assert academic_years_url() == "https://www.assist.org/api/AcademicYears"
    assert institutions_url() == "https://www.assist.org/api/institutions"
    assert categories_url(7, 113, 76) == (
        "https://www.assist.org/api/agreements/categories"
        "?receivingInstitutionId=7&sendingInstitutionId=113&academicYearId=76"
    )
    assert agreements_url(7, 113, 76, "major") == (
        "https://www.assist.org/api/agreements"
        "?receivingInstitutionId=7&sendingInstitutionId=113&academicYearId=76&categoryCode=major"
    )
    assert ROOT_URL == "https://www.assist.org/"


def test_an_agreement_key_is_fully_percent_encoded() -> None:
    key = "76/113/to/7/Major/1c5e2c18-f8e8-477c-f2f8-08ddd3b241a4"

    assert agreement_url(key) == (
        "https://www.assist.org/api/articulation/Agreements"
        "?Key=76%2F113%2Fto%2F7%2FMajor%2F1c5e2c18-f8e8-477c-f2f8-08ddd3b241a4"
    )


# --- payload readers --------------------------------------------------------


def test_community_colleges_come_from_the_flag_sorted_by_id() -> None:
    ids = community_college_ids(fixture("institutions.json"))

    assert len(ids) == 116
    assert list(ids) == sorted(ids)
    assert DEMO_SENDING_ID in ids
    assert DEMO_RECEIVING_ID not in ids  # UCSD is a receiving institution


def test_the_major_category_flag_is_read_from_the_captured_categories() -> None:
    assert major_category_has_reports(fixture("categories_113_to_7_y76.json")) is True
    assert major_category_has_reports(categories(major=False)) is False
    assert major_category_has_reports([]) is False


def test_keyword_matching_is_casefolded_and_substring_based() -> None:
    assert matches_pinned_keyword("Computer Science B.S.")
    assert matches_pinned_keyword("COMPUTER SCIENCE: Bioinformatics B.S.")
    assert matches_pinned_keyword("Molecular Biology B.S.")
    assert not matches_pinned_keyword("Art History B.A.")


def test_a_malformed_list_payload_fails_typed() -> None:
    with pytest.raises(AssistFetchError) as caught:
        community_college_ids({"not": "a list"})

    assert caught.value.assist_reason_code is AssistBuildCode.AGREEMENT_FETCH_FAILED


# --- the walk over the captured demo pair -----------------------------------


def demo_script(**overrides: Scripted) -> Script:
    majors = fixture("agreement_reports_major_113_to_7_y76.json")
    depts = fixture("agreement_reports_dept_113_to_7_y76.json")
    script: Script = {
        academic_years_url(): json_ok(fixture("academic_years.json")),
        institutions_url(): json_ok(fixture("institutions.json")),
        categories_url(7, 113, 76): json_ok(fixture("categories_113_to_7_y76.json")),
        agreements_url(7, 113, 76, "major"): json_ok(majors),
        agreements_url(7, 113, 76, "dept"): json_ok(depts),
    }
    for entry in (*reports_of(majors), *reports_of(depts)):
        script[agreement_url(entry["key"])] = json_ok(AGREEMENT_BODY)
    script.update(overrides)
    return script


def test_the_demo_pair_walk_matches_the_captured_corridor(harness: Harness) -> None:
    transport = harness.transport(demo_script())

    scope = walk_corridor(harness.fetcher(transport), only_pair=DEMO_PAIR)

    assert scope.targets == tuple(sorted(TARGET_IDS))
    assert scope.sending_count == 116
    assert scope.preferred_year_id == PREFERRED_YEAR_ID
    assert len(scope.pairs) == 1
    pair = scope.pairs[0]
    assert (pair.sending_id, pair.receiving_id, pair.year_id) == (113, 7, 76)
    assert (pair.major_reports, pair.major_selected, pair.dept_reports) == (168, 168, 86)
    assert len(pair.agreements) == 168 + 86
    assert pair.fetch_failures == ()
    assert pair.scope_error is None


def test_every_selected_agreement_payload_is_fetched_exactly_once(harness: Harness) -> None:
    transport = harness.transport(demo_script())

    scope = walk_corridor(harness.fetcher(transport), only_pair=DEMO_PAIR)

    keys = [ref.assist_key for ref in scope.pairs[0].agreements]
    assert len(keys) == len(set(keys))
    fetched = [url for url in transport.urls if "articulation/Agreements" in url]
    assert sorted(fetched) == sorted(agreement_url(key) for key in keys)


def test_the_refs_carry_everything_normalize_needs(harness: Harness) -> None:
    transport = harness.transport(demo_script())

    scope = walk_corridor(harness.fetcher(transport), only_pair=DEMO_PAIR)

    majors = [ref for ref in scope.pairs[0].agreements if ref.category == "major"]
    assert majors[0] == AgreementRef(
        assist_key="76/113/to/7/Major/1c5e2c18-f8e8-477c-f2f8-08ddd3b241a4",
        category="major",
        label="Environmental Systems/Ecology, Behavior, and Evolution B.S.",
        sending_id=113,
        receiving_id=7,
        year_id=76,
    )
    assert {ref.category for ref in scope.pairs[0].agreements} == {"major", "dept"}


def test_two_walks_over_equivalent_scripts_produce_equal_scopes(tmp_path: Path) -> None:
    first = Harness(tmp_path / "a")
    second = Harness(tmp_path / "b")

    left = walk_corridor(
        first.fetcher(first.transport(demo_script())),
        only_pair=DEMO_PAIR,
    )
    right = walk_corridor(
        second.fetcher(second.transport(demo_script())),
        only_pair=DEMO_PAIR,
    )

    assert left == right


# --- selection, year fallback, and isolation --------------------------------


def synthetic_script(
    *,
    sending_id: int,
    year_categories: dict[int, object],
    majors: dict[str, object],
    depts: dict[str, object] | None = None,
) -> Script:
    script: Script = {
        academic_years_url(): json_ok([{"id": 76, "fallYear": 2025}]),
        institutions_url(): json_ok([{"id": sending_id, "isCommunityCollege": True}]),
    }
    for year_id, payload in year_categories.items():
        script[categories_url(7, sending_id, year_id)] = json_ok(payload)
    year_id = max(year_categories)
    script[agreements_url(7, sending_id, year_id, "major")] = json_ok(majors)
    if depts is not None:
        script[agreements_url(7, sending_id, year_id, "dept")] = json_ok(depts)
    for entry in reports_of(majors):
        script[agreement_url(entry["key"])] = json_ok(AGREEMENT_BODY)
    return script


def test_a_non_demo_pair_keeps_only_the_pinned_keyword_majors(harness: Harness) -> None:
    majors = report_list(
        ["Computer Science B.S.", "Art History B.A.", "General Biology B.S."],
        prefix="76/114/to/7/Major",
    )
    script = synthetic_script(
        sending_id=OTHER_CC,
        year_categories={PREFERRED_YEAR_ID: categories(major=True)},
        majors=majors,
    )
    transport = harness.transport(script)

    scope = walk_corridor(harness.fetcher(transport), only_pair=(OTHER_CC, 7))

    pair = scope.pairs[0]
    assert (pair.major_reports, pair.major_selected, pair.dept_reports) == (3, 2, 0)
    assert [ref.label for ref in pair.agreements] == [
        "Computer Science B.S.",
        "General Biology B.S.",
    ]
    # Department depth is demo-pair only.
    assert not any("categoryCode=dept" in url for url in transport.urls)


def test_a_year_without_reports_steps_down_to_the_next(harness: Harness) -> None:
    majors = report_list(["Computer Science B.S."], prefix="75/114/to/7/Major")
    script = synthetic_script(
        sending_id=OTHER_CC,
        year_categories={
            PREFERRED_YEAR_ID: categories(major=False),
            PREFERRED_YEAR_ID - 1: categories(major=True),
        },
        majors=majors,
    )
    # `synthetic_script` keys the reports url off the newest scripted year, so
    # rewrite it for the year the fallback is expected to land on.
    script[agreements_url(7, OTHER_CC, PREFERRED_YEAR_ID - 1, "major")] = json_ok(majors)
    transport = harness.transport(script)

    scope = walk_corridor(harness.fetcher(transport), only_pair=(OTHER_CC, 7))

    assert scope.pairs[0].year_id == PREFERRED_YEAR_ID - 1
    assert scope.pairs[0].major_selected == 1


def test_a_pair_with_no_published_year_is_recorded_empty(harness: Harness) -> None:
    script: Script = {
        academic_years_url(): json_ok([]),
        institutions_url(): json_ok([{"id": OTHER_CC, "isCommunityCollege": True}]),
    }
    for offset in range(YEAR_FALLBACK_DEPTH + 1):
        script[categories_url(7, OTHER_CC, PREFERRED_YEAR_ID - offset)] = json_ok(
            categories(major=False)
        )
    transport = harness.transport(script)

    scope = walk_corridor(harness.fetcher(transport), only_pair=(OTHER_CC, 7))

    pair = scope.pairs[0]
    assert pair.year_id is None
    assert pair.agreements == ()
    assert pair.scope_error is None
    assert not any("categoryCode=" in url for url in transport.urls)


def test_a_failed_agreement_fetch_is_isolated_and_the_walk_continues(harness: Harness) -> None:
    majors = report_list(
        ["Computer Science B.S.", "General Biology B.S."], prefix="76/114/to/7/Major"
    )
    script = synthetic_script(
        sending_id=OTHER_CC,
        year_categories={PREFERRED_YEAR_ID: categories(major=True)},
        majors=majors,
    )
    poisoned = reports_of(majors)[0]["key"]
    script[agreement_url(poisoned)] = status(500)
    transport = harness.transport(script)

    scope = walk_corridor(harness.fetcher(transport), only_pair=(OTHER_CC, 7))

    pair = scope.pairs[0]
    assert [ref.label for ref in pair.agreements] == ["General Biology B.S."]
    assert len(pair.fetch_failures) == 1
    failure = pair.fetch_failures[0]
    assert failure.assist_key == poisoned
    assert failure.reason_code is AssistBuildCode.AGREEMENT_FETCH_FAILED
    assert "500" in failure.detail


def test_a_failed_reports_list_ends_the_pair_without_ending_the_walk(harness: Harness) -> None:
    majors = report_list(["Computer Science B.S."], prefix="76/114/to/7/Major")
    script = synthetic_script(
        sending_id=OTHER_CC,
        year_categories={PREFERRED_YEAR_ID: categories(major=True)},
        majors=majors,
    )
    script[agreements_url(7, OTHER_CC, PREFERRED_YEAR_ID, "major")] = raw(b"not json")
    transport = harness.transport(script)

    scope = walk_corridor(harness.fetcher(transport), only_pair=(OTHER_CC, 7))

    pair = scope.pairs[0]
    assert pair.year_id == PREFERRED_YEAR_ID
    assert pair.agreements == ()
    assert pair.scope_error is not None


def test_a_session_failure_is_global_and_is_never_isolated(harness: Harness) -> None:
    """Swallowing this per pair would silently burn hundreds of requests."""
    majors = report_list(["Computer Science B.S."], prefix="76/114/to/7/Major")
    script = synthetic_script(
        sending_id=OTHER_CC,
        year_categories={PREFERRED_YEAR_ID: categories(major=True)},
        majors=majors,
    )
    script[agreement_url(reports_of(majors)[0]["key"])] = status(400)
    transport = FakeHttpTransport(
        {**script, ROOT_URL: [raw(b"<html>"), status(503)]},
        {"X-XSRF-TOKEN": "token"},
    )

    with pytest.raises(AssistFetchError) as caught:
        walk_corridor(harness.fetcher(transport), only_pair=(OTHER_CC, 7))

    assert caught.value.assist_reason_code is AssistBuildCode.SESSION_BOOTSTRAP_FAILED
