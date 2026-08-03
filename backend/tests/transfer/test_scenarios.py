"""One named fixture scenario per `EvaluationFindingCode`, plus the doc 03
edge scenarios, run through the full `build_evaluation` path."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from starmap.contracts.evaluation import Finding
from starmap.contracts.reason_codes import EvaluationFindingCode
from starmap.transfer.evaluate import build_evaluation
from tests.support.clocks import FrozenClock
from tests.support.ids import SequentialIdGenerator
from tests.transfer.scenarios import (
    build_bundle,
    build_requests,
    load_scenario,
    scenario_paths,
    vocabulary_of,
)

CLOCK_START = datetime(2026, 8, 2, tzinfo=UTC)


def comparable(finding: Finding) -> dict[str, Any]:
    """The five doc 03 comparison fields plus citation presence."""
    return {
        "code": finding.code.value,
        "bucket": finding.bucket.value,
        "student_course_codes": list(finding.student_course_codes),
        "receiving_course_code": finding.receiving_course_code,
        "units": finding.units,
        "citation_present": finding.citation is not None,
    }


@pytest.mark.parametrize("path", scenario_paths(), ids=lambda path: path.stem)
def test_scenario(path: Path) -> None:
    scenario = load_scenario(path)
    evaluation = build_evaluation(
        requests=build_requests(scenario["requests"]),
        vocabulary=vocabulary_of(scenario),
        bundle=build_bundle(scenario["bundle"]),
        id_generator=SequentialIdGenerator(),
        clock=FrozenClock(CLOCK_START),
    )
    assert [comparable(finding) for finding in evaluation.findings] == (
        scenario["expected_findings"]
    )
    expected_units = scenario["expected_units"]
    assert evaluation.units.clean_units == expected_units["clean_units"]
    assert evaluation.units.at_risk_units == expected_units["at_risk_units"]
    assert evaluation.units.no_articulation_units == expected_units["no_articulation_units"]
    assert evaluation.units.still_owed_units == expected_units["still_owed_units"]
    assert evaluation.units.at_risk_dollars is None
    assert evaluation.units.no_articulation_dollars is None


def test_every_finding_code_has_a_named_scenario() -> None:
    """The testing-strategy rule: a code without a scenario cannot ship."""
    covered = {
        expected["code"]
        for path in scenario_paths()
        for expected in load_scenario(path)["expected_findings"]
    }
    assert covered == {code.value for code in EvaluationFindingCode}


def test_scenarios_exist() -> None:
    """Guard against a vacuous parametrize if the fixture directory moves."""
    assert len(scenario_paths()) >= 9
