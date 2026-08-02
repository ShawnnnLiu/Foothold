"""The build report: byte stability and typed exclusions.

The report is a committed artifact, so its bytes are the test subject rather
than its Python shape. Every exclusion in it carries a typed `AssistBuildCode`,
which is the "no silent drops" axiom made auditable.
"""

import json
from pathlib import Path
from typing import Any

from starmap.assist.corridor import AgreementRef, CorridorScope, FetchFailure, PairScope
from starmap.assist.normalize import Exclusion, NormalizedAgreement, normalize_agreement
from starmap.assist.report import build_report, pair_report, render_report, write_report
from starmap.contracts.reason_codes import AssistBuildCode

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "assist"
MAJOR_KEY = "76/113/to/7/Major/f8d5b3e6-1d24-4b7a-9a3f-1b2c3d4e5f60"
DEPT_KEY = "76/113/to/7/Department/12"
DE_ANZA = 113
UCSD = 7


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def demo_agreements() -> list[NormalizedAgreement]:
    return [
        normalize_agreement(
            fixture("agreement_major_cse_cs_113_to_7_y76.json"),
            assist_key=MAJOR_KEY,
            category="major",
            label="Mathematics/Computer Science B.S.",
            sending_id=DE_ANZA,
            receiving_id=UCSD,
        ),
        normalize_agreement(
            fixture("agreement_dept_math_113_to_7_y76.json"),
            assist_key=DEPT_KEY,
            category="dept",
            label="Mathematics",
            sending_id=DE_ANZA,
            receiving_id=UCSD,
        ),
    ]


def demo_scope(*, failures: tuple[FetchFailure, ...] = ()) -> PairScope:
    return PairScope(
        sending_id=DE_ANZA,
        receiving_id=UCSD,
        year_id=76,
        major_reports=168,
        major_selected=168,
        dept_reports=86,
        agreements=(
            AgreementRef(
                MAJOR_KEY, "major", "Mathematics/Computer Science B.S.", DE_ANZA, UCSD, 76
            ),
            AgreementRef(DEPT_KEY, "dept", "Mathematics", DE_ANZA, UCSD, 76),
        ),
        fetch_failures=failures,
    )


def report_for(
    scope: PairScope,
    *,
    agreements: list[NormalizedAgreement] | None = None,
    excluded: list[Exclusion] | None = None,
    kind_unknown: int = 33,
    conflicts: int = 0,
) -> Any:
    stored = demo_agreements() if agreements is None else agreements
    pair = pair_report(scope, stored, excluded or [])
    corridor = CorridorScope(
        targets=(7, 39, 117, 120), sending_count=116, preferred_year_id=76, pairs=(scope,)
    )
    return build_report(
        corridor,
        {(scope.sending_id, scope.receiving_id): pair},
        institution_kind_unknown=kind_unknown,
        course_projection_conflicts=conflicts,
    )


def rendered(report: Any) -> Any:
    return json.loads(render_report(report))


# --- shape ------------------------------------------------------------------


def test_the_report_carries_the_corridor_and_the_demo_pair() -> None:
    document = rendered(report_for(demo_scope()))
    assert document["corridor"] == {
        "targets": [7, 39, 117, 120],
        "sending_count": 116,
        "preferred_year_id": 76,
    }
    (pair,) = document["pairs"]
    assert pair["sending_id"] == DE_ANZA
    assert pair["receiving_id"] == UCSD
    assert pair["year_id"] == 76
    assert (pair["major_reports"], pair["major_selected"], pair["dept_reports"]) == (168, 168, 86)


def test_totals_count_what_was_stored_and_what_was_not() -> None:
    document = rendered(report_for(demo_scope()))
    assert document["totals"] == {
        "agreements_stored": 2,
        "agreements_excluded": 0,
        "articulations_excluded": 0,
        "institution_kind_unknown": 33,
        "course_projection_conflicts": 0,
        "advisement_shape_unknown": 0,
    }
    (pair,) = document["pairs"]
    assert pair["articulations_stored"] == 19


def test_a_fetch_failure_appears_as_an_excluded_agreement() -> None:
    """A fetch failure and a parse failure are the same fact to a reviewer,
    differing only in their typed reason code."""
    failure = FetchFailure(
        "76/113/to/7/Major/broken", AssistBuildCode.AGREEMENT_FETCH_FAILED, "HTTP 500"
    )
    document = rendered(report_for(demo_scope(failures=(failure,))))
    (pair,) = document["pairs"]
    assert pair["agreements_excluded"] == [
        {
            "assist_key": "76/113/to/7/Major/broken",
            "reason_code": "agreement_fetch_failed",
            "detail": "HTTP 500",
        }
    ]
    assert document["totals"]["agreements_excluded"] == 1


def test_a_normalize_failure_appears_beside_the_fetch_failures() -> None:
    excluded = [
        Exclusion("76/113/to/7/Major/bad", None, AssistBuildCode.ENVELOPE_INVALID, "not successful")
    ]
    document = rendered(report_for(demo_scope(), excluded=excluded))
    (pair,) = document["pairs"]
    assert [entry["reason_code"] for entry in pair["agreements_excluded"]] == ["envelope_invalid"]


def test_an_articulation_exclusion_carries_its_position() -> None:
    """Position is half the citation, so an exclusion without one could not be
    traced back to a row on assist.org."""
    poisoned = NormalizedAgreement(
        agreement=demo_agreements()[1].agreement,
        exclusions=(
            Exclusion(DEPT_KEY, 4, AssistBuildCode.ADVISEMENT_SHAPE_UNKNOWN, "unknown shape"),
        ),
    )
    document = rendered(report_for(demo_scope(), agreements=[poisoned]))
    (pair,) = document["pairs"]
    assert pair["articulations_excluded"] == [
        {
            "assist_key": DEPT_KEY,
            "position": 4,
            "reason_code": "advisement_shape_unknown",
            "detail": "unknown shape",
        }
    ]
    assert document["totals"]["advisement_shape_unknown"] == 1


def test_every_reported_reason_code_is_a_typed_value() -> None:
    values = {code.value for code in AssistBuildCode}
    excluded = [Exclusion("k", None, AssistBuildCode.FIELD_DECODE_FAILED, "d")]
    document = rendered(report_for(demo_scope(), excluded=excluded))
    for pair in document["pairs"]:
        for entry in (*pair["agreements_excluded"], *pair["articulations_excluded"]):
            assert entry["reason_code"] in values


def test_a_pair_with_no_published_year_reports_a_null_year() -> None:
    scope = PairScope(sending_id=114, receiving_id=UCSD, year_id=None)
    document = rendered(report_for(scope, agreements=[]))
    (pair,) = document["pairs"]
    assert pair["year_id"] is None
    assert pair["agreements_stored"] == 0


# --- determinism ------------------------------------------------------------


def test_the_rendered_report_is_byte_stable_across_runs() -> None:
    assert render_report(report_for(demo_scope())) == render_report(report_for(demo_scope()))


def test_the_report_ends_in_a_newline_and_sorts_its_keys() -> None:
    text = render_report(report_for(demo_scope()))
    assert text.endswith("\n")
    assert text.index('"corridor"') < text.index('"pairs"') < text.index('"totals"')


def test_writing_the_report_twice_produces_identical_bytes(tmp_path: Path) -> None:
    path = tmp_path / "reports" / "assist_build_report.json"
    write_report(path, report_for(demo_scope()))
    first = path.read_bytes()
    write_report(path, report_for(demo_scope()))
    assert path.read_bytes() == first
