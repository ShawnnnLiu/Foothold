"""The exception-handler stack (doc 01 test 3), including the binding TR 4.4
trap: pydantic's `ValidationError` IS a `ValueError` subclass, so an invalid
body must surface as 422, never as the 400 the `ValueError` handler returns."""

from fastapi.testclient import TestClient

from tests.app.conftest import UNINDEXED_CC, demo_body


def test_an_invalid_body_is_422_not_400(client: TestClient) -> None:
    response = client.post("/api/evaluations", json={"sending_institution_id": 113})
    assert response.status_code == 422
    body = response.json()
    assert body["type"] == "validation_error"
    assert body["reason_code"] is None


def test_an_unknown_field_is_rejected(client: TestClient) -> None:
    payload = demo_body() | {"user_id": "mallory"}
    response = client.post("/api/evaluations", json=payload)
    assert response.status_code == 422


def test_an_unknown_major_key_is_a_409_precondition(client: TestClient) -> None:
    payload = demo_body() | {"major_key": "76/113/to/7/Major/no-such-key"}
    response = client.post("/api/evaluations", json=payload)
    assert response.status_code == 409
    body = response.json()
    assert body["type"] == "precondition_failed"
    assert body["reason_code"] == "unknown_agreement"
    assert "76/113/to/7/Major/no-such-key" in body["error"]


def test_an_unindexed_institution_on_autocomplete_is_a_409(client: TestClient) -> None:
    response = client.get(f"/api/cc/{UNINDEXED_CC}/courses", params={"q": "calculus"})
    assert response.status_code == 409
    body = response.json()
    assert body["type"] == "precondition_failed"
    assert body["reason_code"] == "institution_not_indexed"
