"""Loader for the transfer scenario fixtures.

Layout: `tests/fixtures/transfer/<name>.json`, one file per scenario:
`{"comment", "bundle", "requests", "vocabulary"?, "expected_findings",
"expected_units"}`. `vocabulary` defaults to the request codes, so only the
`unresolved` scenario needs to narrow it. Findings are compared on the five
doc 03 fields plus citation presence.
"""

import json
from pathlib import Path
from typing import Any

from starmap.contracts.agreement import Agreement, RequirementGroupAsset
from starmap.contracts.articulation import Articulation
from starmap.transfer.evaluate import AgreementBundle, CourseRequest, DeptAgreement

SCENARIO_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "transfer"


def scenario_paths() -> list[Path]:
    return sorted(SCENARIO_DIR.glob("*.json"))


def load_scenario(path: Path) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads(path.read_text())
    return payload


def build_bundle(raw: dict[str, Any]) -> AgreementBundle:
    return AgreementBundle(
        major=Agreement.model_validate(raw["major"]),
        major_articulations=tuple(
            Articulation.model_validate(entry) for entry in raw["major_articulations"]
        ),
        requirement_groups=tuple(
            RequirementGroupAsset.model_validate(entry) for entry in raw["requirement_groups"]
        ),
        dept_agreements=tuple(
            DeptAgreement(
                agreement=Agreement.model_validate(entry["agreement"]),
                articulations=tuple(
                    Articulation.model_validate(item) for item in entry["articulations"]
                ),
            )
            for entry in raw["dept_agreements"]
        ),
        latest_year_id=raw["latest_year_id"],
        latest_year_label=raw["latest_year_label"],
    )


def build_requests(raw: list[dict[str, Any]]) -> list[CourseRequest]:
    return [CourseRequest(**entry) for entry in raw]


def vocabulary_of(scenario: dict[str, Any]) -> frozenset[str]:
    explicit = scenario.get("vocabulary")
    if explicit is not None:
        return frozenset(explicit)
    return frozenset(entry["course_code"] for entry in scenario["requests"])
