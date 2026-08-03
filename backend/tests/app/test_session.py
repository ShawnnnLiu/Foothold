"""The `sid` trust boundary (doc 01 test 2): minting, persistence, re-minting,
and cross-session isolation."""

import re

from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.app.conftest import demo_body

SET_COOKIE_PATTERN = re.compile(r"sid=(sid_[0-9a-f]+)")


def test_first_response_mints_a_hardened_sid_cookie(client: TestClient) -> None:
    response = client.get("/healthz")
    header = response.headers["set-cookie"]
    assert SET_COOKIE_PATTERN.search(header)
    lowered = header.lower()
    assert "httponly" in lowered
    assert "samesite=lax" in lowered
    assert "path=/" in lowered
    assert "secure" not in lowered  # config.secure_cookies is False here


def test_a_valid_cookie_is_kept_not_reminted(client: TestClient) -> None:
    first = client.get("/healthz")
    minted = SET_COOKIE_PATTERN.search(first.headers["set-cookie"])
    assert minted is not None
    second = client.get("/healthz")
    assert "set-cookie" not in second.headers
    assert client.cookies.get("sid") == minted.group(1)


def test_a_malformed_cookie_is_reminted(client: TestClient) -> None:
    client.cookies.set("sid", "sid_NOTHEX")
    response = client.get("/healthz")
    match = SET_COOKIE_PATTERN.search(response.headers["set-cookie"])
    assert match is not None
    assert match.group(1) != "sid_NOTHEX"


def test_a_well_formed_unknown_sid_is_accepted_as_is(client: TestClient) -> None:
    client.cookies.set("sid", "sid_deadbeef")
    response = client.get("/healthz")
    assert "set-cookie" not in response.headers


def test_sessions_cannot_read_each_others_evaluations(app: FastAPI) -> None:
    session_a = TestClient(app)
    session_b = TestClient(app)
    created = session_a.post("/api/evaluations", json=demo_body())
    assert created.status_code == 200
    evaluation_id = created.json()["evaluation_id"]

    assert session_a.get(f"/api/evaluations/{evaluation_id}").status_code == 200
    denied = session_b.get(f"/api/evaluations/{evaluation_id}")
    assert denied.status_code == 404
    assert denied.json() == {
        "error": "evaluation not found",
        "type": "not_found",
        "reason_code": None,
    }
