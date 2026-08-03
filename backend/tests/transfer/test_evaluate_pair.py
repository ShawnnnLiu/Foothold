"""Targeted classification behavior the scenario comparison fields cannot see:
determinism, single-bucket units attribution, advisement surfacing, series
naming, detail texts, and the deterministic enumeration cap."""

from typing import Any

from starmap.contracts.evaluation import Finding, StudentCourse
from starmap.contracts.reason_codes import EvaluationFindingCode
from starmap.transfer.evaluate import evaluate_pair, units_summary
from tests.transfer.scenarios import SCENARIO_DIR, build_bundle, load_scenario


def scenario_findings(name: str) -> tuple[list[StudentCourse], list[Finding]]:
    scenario = load_scenario(SCENARIO_DIR / f"{name}.json")
    students = [
        StudentCourse(
            course_code=entry["course_code"],
            units=entry["units"],
            resolution=entry.get("resolution", "exact"),
        )
        for entry in scenario["requests"]
        if entry["course_code"] in _vocabulary(scenario)
    ]
    return students, evaluate_pair(students, build_bundle(scenario["bundle"]))


def _vocabulary(scenario: dict[str, Any]) -> set[str]:
    explicit = scenario.get("vocabulary")
    if explicit is not None:
        return set(explicit)
    return {entry["course_code"] for entry in scenario["requests"]}


def by_code(findings: list[Finding], code: EvaluationFindingCode) -> Finding:
    matches = [finding for finding in findings if finding.code is code]
    assert len(matches) == 1, f"expected exactly one {code.value} finding, got {len(matches)}"
    return matches[0]


def test_evaluate_pair_is_deterministic() -> None:
    _, first = scenario_findings("double_count_risk")
    _, second = scenario_findings("double_count_risk")
    assert first == second


def test_a_course_counts_in_exactly_one_bucket() -> None:
    """MATH 1A satisfies both a clean and an advisement articulation; its
    units land once, in its best bucket, and never in at-risk."""
    students, findings = scenario_findings("double_count_risk")
    summary = units_summary(students, findings)
    assert summary.clean_units == 5.0
    assert summary.at_risk_units == 0.0


def test_units_summary_dollars_use_the_target_rate_with_rounding() -> None:
    """The locked doc 03 formula: units * target rate, rounded to 2 places;
    zero at-risk units price to 0.0 (a real answer), never None."""
    students, findings = scenario_findings("no_articulation")
    summary = units_summary(students, findings, target_rate=33.3333)
    assert summary.no_articulation_units == 4.0
    assert summary.no_articulation_dollars == 133.33
    assert summary.at_risk_dollars == 0.0


def test_units_summary_without_a_rate_leaves_dollars_none() -> None:
    students, findings = scenario_findings("no_articulation")
    summary = units_summary(students, findings)
    assert summary.at_risk_dollars is None
    assert summary.no_articulation_dollars is None


def test_double_count_cites_the_first_involved_articulation() -> None:
    _, findings = scenario_findings("double_count_risk")
    finding = by_code(findings, EvaluationFindingCode.DOUBLE_COUNT_RISK)
    assert finding.citation is not None
    assert finding.citation.position == 0
    assert finding.detail is not None
    assert finding.detail.endswith(":0, 76/113/to/7/Major/d2dfb7a8-d505-4e70-f33c-08ddd3b241a4:1")


def test_partial_series_detail_names_matched_and_missing() -> None:
    _, findings = scenario_findings("partial_series")
    finding = by_code(findings, EvaluationFindingCode.PARTIAL_SERIES)
    assert finding.detail == "matched MATH 1C; missing MATH 1D"


def test_advisement_note_carries_the_advisement_text() -> None:
    _, findings = scenario_findings("advisement_note")
    finding = by_code(findings, EvaluationFindingCode.ADVISEMENT_NOTE)
    assert finding.advisements == ["Minimum grade required: C or better"]


def test_owed_group_advisements_ride_the_still_owed_finding() -> None:
    """The amendment: group advisements surface on the still-owed finding."""
    _, findings = scenario_findings("select_courses_pool")
    finding = by_code(findings, EvaluationFindingCode.STILL_OWED)
    assert finding.advisements == ["Minimum grade required: B or better"]
    assert finding.detail == "complete 1 more from: CHEM 6B or CHEM 6C"


def test_series_finding_quotes_the_series_name() -> None:
    _, findings = scenario_findings("series_receiving")
    finding = by_code(findings, EvaluationFindingCode.TRANSFERS_CLEAN)
    assert finding.receiving_course_code is None
    assert finding.receiving_course_title == "PHYSICS 2A, PHYSICS 2B"


def test_owed_or_series_cell_costs_the_cheapest_course() -> None:
    _, findings = scenario_findings("series_cell_owed")
    finding = by_code(findings, EvaluationFindingCode.STILL_OWED)
    assert finding.receiving_course_code is None
    assert finding.receiving_course_title == "MATH 10A or MATH 20A"
    assert finding.units == 3.0


def test_or_group_detail_joins_owed_cells_with_or() -> None:
    _, findings = scenario_findings("or_requirement_group")
    finding = by_code(findings, EvaluationFindingCode.STILL_OWED)
    assert finding.detail == "CSE 15L or CSE 29"
    assert finding.citation is not None
    assert finding.citation.position == 0


def test_stale_year_surfaces_in_detail_when_a_note_outranks_it() -> None:
    """Lower-priority at-risk factors are surfaced in detail, not dropped."""
    scenario = load_scenario(SCENARIO_DIR / "stale_year.json")
    articulation = scenario["bundle"]["dept_agreements"][0]["articulations"][0]
    articulation["advisements"] = ["Complete entire sequence at same institution prior to transfer"]
    students = [StudentCourse(course_code="CIS 22C", units=4.5, resolution="exact")]
    findings = evaluate_pair(students, build_bundle(scenario["bundle"]))
    finding = by_code(findings, EvaluationFindingCode.ADVISEMENT_NOTE)
    assert finding.detail is not None
    assert "2024-2025 predates the latest published year 2025-2026" in finding.detail


def test_select_pool_enumeration_caps_at_eight_labels() -> None:
    """A wide pool truncates deterministically instead of overflowing detail."""
    scenario = load_scenario(SCENARIO_DIR / "select_courses_pool.json")
    group = scenario["bundle"]["requirement_groups"][0]
    group["sections"][0]["cells"] = [
        {
            "cell_id": f"00000000-0000-4000-8000-{number:012d}",
            "course": {
                "course_code": f"CHEM {number}B",
                "prefix": "CHEM",
                "number": f"{number}B",
                "title": "General Chemistry",
                "units_min": 4.0,
                "units_max": 4.0,
            },
        }
        for number in range(10, 21)
    ]
    findings = evaluate_pair([], build_bundle(scenario["bundle"]))
    finding = by_code(findings, EvaluationFindingCode.STILL_OWED)
    assert finding.detail is not None
    assert finding.detail.startswith("complete 2 more from: CHEM 10B or ")
    assert finding.detail.endswith(" or 3 more options")
    assert finding.detail.count(" or ") == 8
