"""The four LLM wire routes (doc 03) against FakeTransport-backed nodes.

TestClient runs background tasks synchronously inside the request cycle, so
polls in this module observe FINAL states; the `pending` wire shape is covered
by the store tests and the contract fixtures rather than fought with threads.

Letters are computed with the node's own template renderer over a
deterministic twin of the evaluation the route will store: the fixture
evaluation differs only in its minted id and timestamp, neither of which
enters the letter or the citation vocabulary.
"""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from starmap.app.web.app import create_app
from starmap.app.web.config import AppConfig
from starmap.contracts.evaluation import Evaluation
from starmap.contracts.petition import Petition
from starmap.contracts.reason_codes import LlmReasonCode
from starmap.contracts.transcript_parse import TranscriptParse
from starmap.llm.errors import TransportError
from starmap.llm.petition_writer import build_findings_bundle, render_template_letter
from tests.app.conftest import DE_ANZA, MAJOR_LABEL, UNINDEXED_CC, demo_body
from tests.support.transports import FakeTransport, success

PASTE_PATH = (
    Path(__file__).resolve().parents[3] / "data" / "curated" / "demo_students"
) / "deanza_ucsd_cs_paste.txt"
PASTE_TEXT = PASTE_PATH.read_text(encoding="utf-8")

SENDING_NAME = "De Anza College"
RECEIVING_NAME = "University of California, San Diego"

SELECTABLE = {"at_risk", "no_articulation"}

# Grounded in the paste text; PHYS 4A is the demo's out-of-vocabulary course.
DEMO_PROPOSAL = {
    "courses": [
        {"course_code": "MATH 1A", "title": "Calculus I", "units": 5.0, "term": "Fall 2024"},
        {"course_code": "MATH 1B", "title": "Calculus II", "units": 5.0, "term": "Winter 2025"},
        {"course_code": "MATH 1C", "title": "Calculus III", "units": 5.0, "term": "Spring 2025"},
        {
            "course_code": "CIS 36B",
            "title": "Intermediate Problem Solving in Java",
            "units": 4.5,
            "term": "Fall 2025",
        },
        {
            "course_code": "CIS 22C",
            "title": "Data Abstraction and Structures",
            "units": 4.5,
            "term": "Winter 2026",
        },
        {
            "course_code": "PHYS 4A",
            "title": "Physics for Scientists and Engineers: Mechanics",
            "units": 6.0,
            "term": "Spring 2026",
        },
    ]
}
RESOLVABLE_CODES = ["MATH 1A", "MATH 1B", "MATH 1C", "CIS 36B", "CIS 22C"]

# Grounding rejects this every attempt, so three of them exhaust repair.
UNGROUNDED_PROPOSAL = {
    "courses": [
        {
            "course_code": "CHEM 999",
            "title": "Introduction to Chemistry",
            "units": None,
            "term": None,
        }
    ]
}

AUTH_ERROR = TransportError(
    "AuthenticationError", retryable=False, reason_code=LlmReasonCode.AUTH_FAILED
)


@pytest.fixture(autouse=True)
def _no_env_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """`create_app` without a transport must stay disabled even on a keyed machine."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def llm_app(app_config: AppConfig, script: list[Any]) -> FastAPI:
    return create_app(app_config, llm_transport=FakeTransport(script))


def create_evaluation(client: TestClient) -> dict[str, Any]:
    response = client.post("/api/evaluations", json=demo_body())
    assert response.status_code == 200
    return dict(response.json())


def selectable_positions(evaluation: dict[str, Any]) -> list[int]:
    return [
        position
        for position, finding in enumerate(evaluation["findings"])
        if finding["bucket"] in SELECTABLE
    ]


def template_letter(evaluation: dict[str, Any], positions: list[int]) -> str:
    bundle = build_findings_bundle(
        Evaluation.model_validate(evaluation),
        positions,
        sending_name=SENDING_NAME,
        receiving_name=RECEIVING_NAME,
        major_label=MAJOR_LABEL,
    )
    return render_template_letter(bundle)


def demo_letter(app_config: AppConfig) -> str:
    """The valid letter every petition script builds on, computed from a
    deterministic twin of the evaluation (module docstring)."""
    probe = TestClient(create_app(app_config))
    evaluation = create_evaluation(probe)
    return template_letter(evaluation, selectable_positions(evaluation))


def post_petition(client: TestClient, evaluation_id: str, positions: list[int]) -> Any:
    return client.post(
        f"/api/evaluations/{evaluation_id}/petition", json={"finding_positions": positions}
    )


# --- petition ----------------------------------------------------------------


def test_petition_happy_path(app_config: AppConfig) -> None:
    letter = demo_letter(app_config)
    client = TestClient(llm_app(app_config, [success({"letter_text": letter})]))
    evaluation = create_evaluation(client)
    positions = selectable_positions(evaluation)

    created = post_petition(client, evaluation["evaluation_id"], positions)
    assert created.status_code == 202
    petition_id = created.json()["petition_id"]
    assert petition_id.startswith("pet_")

    polled = client.get(f"/api/petitions/{petition_id}")
    assert polled.status_code == 200
    body = polled.json()
    assert set(body.keys()) == {"status", "reason_code", "fallback", "letter_text", "cited"}
    assert body["status"] == "succeeded"
    assert body["reason_code"] is None
    assert body["fallback"] is False
    assert body["letter_text"] == letter
    assert body["cited"]
    assert all(set(entry.keys()) == {"course_code", "finding_position"} for entry in body["cited"])
    assert all(entry["finding_position"] in positions for entry in body["cited"])


def test_petition_fallback_after_repair_exhaustion(app_config: AppConfig) -> None:
    letter = demo_letter(app_config)
    invented = letter + "\n\nI also completed CS 999 with distinction."
    client = TestClient(llm_app(app_config, [success({"letter_text": invented})] * 3))
    evaluation = create_evaluation(client)
    positions = selectable_positions(evaluation)

    petition_id = post_petition(client, evaluation["evaluation_id"], positions).json()[
        "petition_id"
    ]
    body = client.get(f"/api/petitions/{petition_id}").json()

    assert body["status"] == "succeeded"
    assert body["fallback"] is True
    assert body["reason_code"] == "repair_limit_exceeded"
    assert body["letter_text"] == template_letter(evaluation, positions)


def test_petition_failed_is_http_200_with_the_typed_reason(app_config: AppConfig) -> None:
    client = TestClient(llm_app(app_config, [AUTH_ERROR]))
    evaluation = create_evaluation(client)

    petition_id = post_petition(
        client, evaluation["evaluation_id"], selectable_positions(evaluation)
    ).json()["petition_id"]
    polled = client.get(f"/api/petitions/{petition_id}")

    assert polled.status_code == 200
    body = polled.json()
    assert body["status"] == "failed"
    assert body["reason_code"] == "auth_failed"
    assert body["letter_text"] is None
    assert body["cited"] == []


def test_petition_404s_are_uniform(app_config: AppConfig) -> None:
    app = llm_app(app_config, [])
    session_a = TestClient(app)
    session_b = TestClient(app)
    evaluation = create_evaluation(session_a)
    positions = selectable_positions(evaluation)

    not_found = {"error": "evaluation not found", "type": "not_found", "reason_code": None}
    unknown = post_petition(session_a, "eval_0000000000000000", positions)
    assert (unknown.status_code, unknown.json()) == (404, not_found)
    cross_session = post_petition(session_b, evaluation["evaluation_id"], positions)
    assert (cross_session.status_code, cross_session.json()) == (404, not_found)

    polled = session_a.get("/api/petitions/pet_0000000000000000")
    assert polled.status_code == 404
    assert polled.json() == {
        "error": "petition not found",
        "type": "not_found",
        "reason_code": None,
    }


def test_petition_422s_reject_bad_positions(app_config: AppConfig) -> None:
    client = TestClient(llm_app(app_config, []))
    evaluation = create_evaluation(client)
    evaluation_id = evaluation["evaluation_id"]
    clean = next(
        position
        for position, finding in enumerate(evaluation["findings"])
        if finding["bucket"] == "transfers_clean"
    )
    valid = selectable_positions(evaluation)[0]

    assert post_petition(client, evaluation_id, []).status_code == 422
    assert post_petition(client, evaluation_id, [valid, valid]).status_code == 422
    out_of_range = post_petition(client, evaluation_id, [len(evaluation["findings"])])
    assert out_of_range.status_code == 422
    assert str(len(evaluation["findings"])) in out_of_range.json()["error"]
    assert post_petition(client, evaluation_id, [clean]).status_code == 422


def test_petition_post_attaches_while_the_same_selection_is_pending(
    app_config: AppConfig,
) -> None:
    """Decision 6 as amended 2026-08-20: a live pending selection is attached
    to (202 with the existing id), never duplicated and never a 409."""
    app = llm_app(app_config, [])
    client = TestClient(app)
    evaluation = create_evaluation(client)
    positions = selectable_positions(evaluation)
    sid = client.cookies.get("sid")
    assert sid is not None
    # TestClient finishes background jobs before the response returns, so the
    # live pending row is planted at the store seam with a fresh clock stamp.
    app.state.petitions.put(
        sid,
        Petition(
            petition_id="pet_0000000000000000",
            evaluation_id=evaluation["evaluation_id"],
            finding_positions=sorted(positions),
            status="pending",
            created_at=datetime.now(UTC),
        ),
    )

    response = post_petition(client, evaluation["evaluation_id"], positions)

    assert response.status_code == 202
    assert response.json() == {"petition_id": "pet_0000000000000000"}
    # The empty FakeTransport script proves no duplicate job ran: attaching
    # never consumes an LLM call, and the planted row stays pending.
    polled = client.get("/api/petitions/pet_0000000000000000")
    assert polled.status_code == 200
    assert polled.json()["status"] == "pending"


def test_petition_post_reuses_the_succeeded_letter(app_config: AppConfig) -> None:
    """The 2026-08-21 decision 6 amendment: re-selecting a combination whose
    letter already exists replays it instead of spending a fresh LLM call."""
    letter = demo_letter(app_config)
    app = llm_app(app_config, [success({"letter_text": letter})])
    client = TestClient(app)
    evaluation = create_evaluation(client)
    positions = selectable_positions(evaluation)

    first = post_petition(client, evaluation["evaluation_id"], positions)
    assert first.status_code == 202
    petition_id = first.json()["petition_id"]
    # TestClient ran the background job synchronously, so the row is now
    # succeeded; the script is exhausted, proving the repeat spends nothing.
    repeat = post_petition(client, evaluation["evaluation_id"], positions)
    assert repeat.status_code == 202
    assert repeat.json() == {"petition_id": petition_id}
    polled = client.get(f"/api/petitions/{petition_id}")
    assert polled.json()["status"] == "succeeded"
    assert polled.json()["letter_text"] == letter


def test_petition_post_never_reuses_a_fallback_letter(app_config: AppConfig) -> None:
    """A template letter after repair exhaustion must not pin the selection:
    the next POST gets a fresh LLM attempt."""
    letter = demo_letter(app_config)
    app = llm_app(app_config, [success({"letter_text": letter})])
    client = TestClient(app)
    evaluation = create_evaluation(client)
    positions = selectable_positions(evaluation)
    sid = client.cookies.get("sid")
    assert sid is not None
    app.state.petitions.put(
        sid,
        Petition(
            petition_id="pet_0000000000000000",
            evaluation_id=evaluation["evaluation_id"],
            finding_positions=sorted(positions),
            status="succeeded",
            fallback=True,
            reason_code=LlmReasonCode.REPAIR_LIMIT_EXCEEDED,
            letter_text=letter,
            created_at=datetime.now(UTC),
        ),
    )

    response = post_petition(client, evaluation["evaluation_id"], positions)

    assert response.status_code == 202
    fresh_id = response.json()["petition_id"]
    assert fresh_id != "pet_0000000000000000"
    polled = client.get(f"/api/petitions/{fresh_id}")
    assert polled.json()["status"] == "succeeded"
    assert polled.json()["fallback"] is False


def test_petition_run_writes_call_log_rows_under_its_id(app_config: AppConfig) -> None:
    letter = demo_letter(app_config)
    app = llm_app(app_config, [success({"letter_text": letter})])
    client = TestClient(app)
    evaluation = create_evaluation(client)

    petition_id = post_petition(
        client, evaluation["evaluation_id"], selectable_positions(evaluation)
    ).json()["petition_id"]

    rows = app.state.call_log.list_for_run(petition_id)
    assert rows
    assert all(row.node.value == "petition_writer" for row in rows)


# --- transcript parse --------------------------------------------------------


def post_parse(client: TestClient, text: str = PASTE_TEXT, institution: int = DE_ANZA) -> Any:
    return client.post(
        "/api/transcript/parse", json={"text": text, "sending_institution_id": institution}
    )


def test_parse_happy_path(app_config: AppConfig) -> None:
    client = TestClient(llm_app(app_config, [success(DEMO_PROPOSAL)]))

    created = post_parse(client)
    assert created.status_code == 202
    parse_id = created.json()["parse_id"]
    assert parse_id.startswith("parse_")

    polled = client.get(f"/api/transcript/{parse_id}")
    assert polled.status_code == 200
    body = polled.json()
    assert set(body.keys()) == {"status", "reason_code", "chips", "unresolved"}
    assert body["status"] == "succeeded"
    assert body["reason_code"] is None
    assert [chip["course_code"] for chip in body["chips"]] == RESOLVABLE_CODES
    assert all(chip["resolution"] == "exact" for chip in body["chips"])
    assert all(
        set(chip.keys()) == {"course_code", "title", "units_min", "units_max", "resolution"}
        for chip in body["chips"]
    )
    assert body["unresolved"] == [
        {
            "proposed_code": "PHYS 4A",
            "proposed_title": "Physics for Scientists and Engineers: Mechanics",
        }
    ]


def test_parse_failed_after_repair_exhaustion(app_config: AppConfig) -> None:
    client = TestClient(llm_app(app_config, [success(UNGROUNDED_PROPOSAL)] * 3))

    parse_id = post_parse(client).json()["parse_id"]
    body = client.get(f"/api/transcript/{parse_id}").json()

    assert body["status"] == "failed"
    assert body["reason_code"] == "repair_limit_exceeded"
    assert body["chips"] == []
    assert body["unresolved"] == []


def test_parse_409_for_an_unindexed_institution(app_config: AppConfig) -> None:
    client = TestClient(llm_app(app_config, []))

    response = post_parse(client, institution=UNINDEXED_CC)

    assert response.status_code == 409
    assert response.json()["reason_code"] == "institution_not_indexed"


def test_parse_422s_reject_bad_bodies(app_config: AppConfig) -> None:
    client = TestClient(llm_app(app_config, []))

    assert post_parse(client, text="").status_code == 422
    assert post_parse(client, text="x" * 20001).status_code == 422
    missing = client.post("/api/transcript/parse", json={"text": "MATH 1A"})
    assert missing.status_code == 422
    assert post_parse(client, institution=0).status_code == 422


# --- the availability gate ---------------------------------------------------


def test_llm_disabled_409s_both_posts_but_still_serves_polls(app_config: AppConfig) -> None:
    app = create_app(app_config)
    assert app.state.llm is None
    client = TestClient(app)
    evaluation = create_evaluation(client)
    sid = client.cookies.get("sid")
    assert sid is not None

    parse_denied = post_parse(client)
    assert parse_denied.status_code == 409
    assert parse_denied.json()["reason_code"] == "llm_unavailable"
    petition_denied = post_petition(
        client, evaluation["evaluation_id"], selectable_positions(evaluation)
    )
    assert petition_denied.status_code == 409
    assert petition_denied.json()["reason_code"] == "llm_unavailable"

    app.state.parses.put(
        sid,
        TranscriptParse(
            parse_id="parse_0000000000000000",
            sending_institution_id=DE_ANZA,
            status="pending",
            created_at=datetime.now(UTC),
        ),
    )
    polled = client.get("/api/transcript/parse_0000000000000000")
    assert polled.status_code == 200
    assert polled.json()["status"] == "pending"


# --- session isolation -------------------------------------------------------


def test_sessions_cannot_read_each_others_jobs(app_config: AppConfig) -> None:
    letter = demo_letter(app_config)
    app = llm_app(app_config, [success(DEMO_PROPOSAL), success({"letter_text": letter})])
    session_a = TestClient(app)
    session_b = TestClient(app)
    evaluation = create_evaluation(session_a)
    parse_id = post_parse(session_a).json()["parse_id"]
    petition_id = post_petition(
        session_a, evaluation["evaluation_id"], selectable_positions(evaluation)
    ).json()["petition_id"]

    assert session_a.get(f"/api/transcript/{parse_id}").status_code == 200
    assert session_a.get(f"/api/petitions/{petition_id}").status_code == 200
    assert session_b.get(f"/api/transcript/{parse_id}").status_code == 404
    assert session_b.get(f"/api/petitions/{petition_id}").status_code == 404
