"""The deterministic API surface (doc 01 test 4), pinned against the fixture
pair: De Anza (113) -> UCSD (7), the captured major + MATH department
agreements, and the fixture cost table."""

from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from starmap.app.web.config import AppConfig
from starmap.common.sqlite import SqliteDatabase
from starmap.contracts.arbitrage import ArbitrageRow
from starmap.contracts.evaluation import Evaluation
from starmap.retrieval.index import CourseIndex
from tests.app.conftest import (
    DE_ANZA,
    MAJOR_KEY,
    MAJOR_LABEL,
    UCSD,
    YEAR_LABEL,
    demo_body,
)

# --- institutions ------------------------------------------------------------


def test_institutions_filters_to_ccs(client: TestClient) -> None:
    response = client.get("/api/institutions", params={"kind": "cc"})
    assert response.status_code == 200
    rows = response.json()["institutions"]
    assert rows and all(row["kind"] == "cc" for row in rows)
    assert any(row["assist_id"] == DE_ANZA for row in rows)
    assert rows == sorted(rows, key=lambda row: (row["name"], row["assist_id"]))


def test_institutions_filters_to_targets(client: TestClient) -> None:
    response = client.get("/api/institutions", params={"kind": "target"})
    assert response.status_code == 200
    rows = response.json()["institutions"]
    assert rows and all(row["kind"] in {"uc", "csu"} for row in rows)
    assert any(row["assist_id"] == UCSD for row in rows)
    assert rows == sorted(rows, key=lambda row: (row["name"], row["assist_id"]))


def test_institutions_kind_is_required_and_closed(client: TestClient) -> None:
    assert client.get("/api/institutions").status_code == 422
    assert client.get("/api/institutions", params={"kind": "university"}).status_code == 422


# --- majors ------------------------------------------------------------------


def test_majors_lists_the_fixture_pair(client: TestClient) -> None:
    response = client.get(f"/api/pairs/{DE_ANZA}/{UCSD}/majors")
    assert response.status_code == 200
    assert response.json() == {
        "majors": [{"assist_key": MAJOR_KEY, "label": MAJOR_LABEL, "year_label": YEAR_LABEL}]
    }


def test_majors_for_an_unknown_pair_is_an_empty_200(client: TestClient) -> None:
    response = client.get(f"/api/pairs/{DE_ANZA}/{DE_ANZA + 1}/majors")
    assert response.status_code == 200
    assert response.json() == {"majors": []}


# --- autocomplete ------------------------------------------------------------


def test_autocomplete_returns_index_order(client: TestClient, app_config: AppConfig) -> None:
    response = client.get(f"/api/cc/{DE_ANZA}/courses", params={"q": "calculus"})
    assert response.status_code == 200
    rows = response.json()["courses"]
    assert 0 < len(rows) <= 8

    db = SqliteDatabase(app_config.corpus_db)
    try:
        hits = CourseIndex(db).search(DE_ANZA, "calculus", k=8)
    finally:
        db.close()
    assert [row["course_code"] for row in rows] == [hit.course_code for hit in hits]
    assert rows[0].keys() == {"course_code", "title", "units_min", "units_max"}


def test_autocomplete_requires_a_non_blank_query(client: TestClient) -> None:
    assert client.get(f"/api/cc/{DE_ANZA}/courses").status_code == 422
    assert client.get(f"/api/cc/{DE_ANZA}/courses", params={"q": ""}).status_code == 422
    assert client.get(f"/api/cc/{DE_ANZA}/courses", params={"q": "   "}).status_code == 422


# --- evaluations -------------------------------------------------------------


def _finding_keys(document: dict[str, Any]) -> set[tuple[str, ...]]:
    return {
        (
            finding["code"],
            ",".join(finding["student_course_codes"]),
            finding["receiving_course_code"] or finding["receiving_course_title"] or "",
        )
        for finding in document["findings"]
    }


def test_post_evaluations_returns_the_bare_evaluation_contract(client: TestClient) -> None:
    response = client.post("/api/evaluations", json=demo_body())
    assert response.status_code == 200
    document = response.json()
    assert set(document.keys()) == set(Evaluation.model_fields.keys())

    evaluation = Evaluation.model_validate(document)
    assert evaluation.sending_institution_id == DE_ANZA
    assert evaluation.receiving_institution_id == UCSD
    assert evaluation.major_key == MAJOR_KEY
    assert evaluation.year_label == YEAR_LABEL

    # The fixture student's hand-derived totals; the fixture UCSD rate mirrors
    # the real one, so at-risk dollars read like the verified demo.
    assert evaluation.units.clean_units == 19.0
    assert evaluation.units.at_risk_units == 5.0
    assert evaluation.units.no_articulation_units == 0.0
    assert evaluation.units.still_owed_units == 18.0
    assert evaluation.units.at_risk_dollars == 1455.0
    assert evaluation.units.no_articulation_dollars == 0.0

    keys = _finding_keys(document)
    assert ("transfers_clean", "MATH 1A", "MATH 20A") in keys
    assert ("partial_series", "MATH 1C", "MATH 20C") in keys
    assert ("partial_series", "MATH 1C", "MATH 20E") in keys
    assert ("unresolved", "PHYS 4A", "") in keys
    partials = [f for f in document["findings"] if f["code"] == "partial_series"]
    assert all("missing MATH 1D" in f["detail"] for f in partials)


def test_post_normalizes_codes_and_ignores_client_units(client: TestClient) -> None:
    body = demo_body()
    body["courses"] = [{"course_code": "  math 1a "}]
    response = client.post("/api/evaluations", json=body)
    assert response.status_code == 200
    course = response.json()["student_courses"][0]
    # Units and title come from the `cc_courses` projection, never the client.
    assert course["course_code"] == "MATH 1A"
    assert course["units"] == 5.0
    assert course["title"] == "Calculus I"


def test_post_rejects_duplicate_codes_quoting_the_duplicate(client: TestClient) -> None:
    body = demo_body()
    body["courses"] = [{"course_code": "MATH 1A"}, {"course_code": " math 1a"}]
    response = client.post("/api/evaluations", json=body)
    assert response.status_code == 422
    assert "MATH 1A" in response.json()["error"]


def test_post_rejects_client_supplied_units(client: TestClient) -> None:
    body = demo_body()
    body["courses"] = [{"course_code": "MATH 1A", "units": 99.0}]
    assert client.post("/api/evaluations", json=body).status_code == 422


def test_an_unknown_code_becomes_an_unresolved_finding(client: TestClient) -> None:
    body = demo_body()
    body["courses"] = [{"course_code": "MATH 1A"}, {"course_code": "PHYS 4A"}]
    document = client.post("/api/evaluations", json=body).json()
    unresolved = [f for f in document["findings"] if f["code"] == "unresolved"]
    assert [f["student_course_codes"] for f in unresolved] == [["PHYS 4A"]]
    codes = [course["course_code"] for course in document["student_courses"]]
    assert codes == ["MATH 1A"]


def test_get_returns_the_stored_evaluation_byte_identically(client: TestClient) -> None:
    created = client.post("/api/evaluations", json=demo_body())
    assert created.status_code == 200
    evaluation_id = created.json()["evaluation_id"]
    fetched = client.get(f"/api/evaluations/{evaluation_id}")
    assert fetched.status_code == 200
    assert fetched.content == created.content


def test_get_with_an_unknown_id_is_a_404(client: TestClient) -> None:
    response = client.get("/api/evaluations/eval_0000000000000000")
    assert response.status_code == 404
    assert response.json() == {
        "error": "evaluation not found",
        "type": "not_found",
        "reason_code": None,
    }


# --- arbitrage ---------------------------------------------------------------


def _create_evaluation_id(client: TestClient) -> str:
    created = client.post("/api/evaluations", json=demo_body())
    assert created.status_code == 200
    return str(created.json()["evaluation_id"])


def test_arbitrage_round_trip_on_the_fixture_store(client: TestClient) -> None:
    """The fixture student against the captured major agreement: every row's
    dollars are exactly `units * (291 - 46)`, equal savings tie-break on
    position, and the partial series sells only its missing member."""
    evaluation_id = _create_evaluation_id(client)
    response = client.get("/api/arbitrage", params={"evaluation_id": evaluation_id})
    assert response.status_code == 200
    payload = response.json()
    assert set(payload.keys()) == {"rows", "omitted_no_rate", "cc_per_unit", "target_per_unit"}
    assert payload["omitted_no_rate"] == 0
    assert payload["cc_per_unit"] == 46.0
    assert payload["target_per_unit"] == 291.0

    rows = [ArbitrageRow.model_validate(entry) for entry in payload["rows"]]
    assert [
        (row.missing_course_codes, row.receiving_course_code, row.citation.position) for row in rows
    ] == [
        (["MATH 2A"], "MATH 20D", 0),
        (["MATH 2B"], "MATH 18", 2),
        (["MATH 1D"], "MATH 20E", 3),
        (["MATH 1D"], "MATH 20C", 4),
    ]
    for row in rows:
        assert row.savings_dollars == row.units * (291.0 - 46.0)


def test_arbitrage_ranking_is_server_truth(client: TestClient) -> None:
    """The wire order IS the ranking: dollar rows descending with position
    tie-break, exactly what the client renders without re-sorting."""
    evaluation_id = _create_evaluation_id(client)
    payload = client.get("/api/arbitrage", params={"evaluation_id": evaluation_id}).json()
    keys = [
        (
            row["savings_dollars"] is None,
            -(row["savings_dollars"] or 0.0),
            row["citation"]["position"],
        )
        for row in payload["rows"]
    ]
    assert keys == sorted(keys)


def test_arbitrage_with_an_unknown_id_is_a_404(client: TestClient) -> None:
    response = client.get("/api/arbitrage", params={"evaluation_id": "eval_0000000000000000"})
    assert response.status_code == 404
    assert response.json() == {
        "error": "evaluation not found",
        "type": "not_found",
        "reason_code": None,
    }


def test_arbitrage_requires_the_evaluation_id_query(client: TestClient) -> None:
    assert client.get("/api/arbitrage").status_code == 422


def test_sessions_cannot_read_each_others_arbitrage(app: FastAPI) -> None:
    session_a = TestClient(app)
    session_b = TestClient(app)
    evaluation_id = _create_evaluation_id(session_a)

    assert (
        session_a.get("/api/arbitrage", params={"evaluation_id": evaluation_id}).status_code == 200
    )
    denied = session_b.get("/api/arbitrage", params={"evaluation_id": evaluation_id})
    assert denied.status_code == 404
    assert denied.json() == {
        "error": "evaluation not found",
        "type": "not_found",
        "reason_code": None,
    }


def test_stored_rows_revalidate_through_the_contract() -> None:
    """The store's read path is rebuild-through-validation: a drifted payload
    must fail loudly, so this asserts the contract actually rejects one."""
    try:
        Evaluation.model_validate_json('{"evaluation_id": "eval_x"}')
    except ValidationError:
        pass
    else:
        raise AssertionError("a drifted payload validated cleanly")
