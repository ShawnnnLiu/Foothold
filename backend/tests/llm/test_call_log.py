"""The append-only call-log store, against real SQLite (never faked)."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest

from starmap.common.sqlite import SqliteDatabase
from starmap.contracts.llm_call_log import LlmCallLogRecord, LlmNode
from starmap.contracts.reason_codes import LlmReasonCode
from starmap.llm.call_log import COMPONENT, SCHEMA_VERSION, CallLogAlreadyExistsError
from starmap.llm.call_log import SqliteCallLogStore as Store

CREATED_AT = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)


def record(
    index: int,
    *,
    run_id: str = "run_a",
    outcome: Literal["pass", "fail"] = "pass",
    reason_code: LlmReasonCode | None = None,
) -> LlmCallLogRecord:
    return LlmCallLogRecord(
        llm_call_log_id=f"llm_call_{index:016d}",
        run_id=run_id,
        node=LlmNode.TRANSCRIPT_PARSER,
        prompt_version="test-node-v1",
        model_name="claude-sonnet-5",
        attempt=0,
        sdk_retry=0,
        input_tokens=10,
        output_tokens=5,
        cache_creation_tokens=0,
        cache_read_tokens=0,
        cost_estimate_usd=0.000105,
        latency_ms=12,
        validation_outcome=outcome,
        reason_code=reason_code,
        cache_hit=False,
        truncated=False,
        refusal=False,
        prompt_hash="a" * 64,
        response_hash="b" * 64,
        created_at=CREATED_AT,
    )


def test_append_then_read_back_round_trips(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "sessions.db")
    store = Store(db)

    store.append(record(1))

    (stored,) = store.list_all()
    assert stored == record(1)
    db.close()


def test_rows_come_back_in_insertion_order(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "sessions.db")
    store = Store(db)
    for index in (3, 1, 2):
        store.append(record(index))

    assert [row.llm_call_log_id for row in store.list_all()] == [
        "llm_call_0000000000000003",
        "llm_call_0000000000000001",
        "llm_call_0000000000000002",
    ]
    db.close()


def test_list_for_run_filters_by_run_id(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "sessions.db")
    store = Store(db)
    store.append(record(1, run_id="run_a"))
    store.append(record(2, run_id="run_b"))
    store.append(record(3, run_id="run_a"))

    assert [row.llm_call_log_id for row in store.list_for_run("run_a")] == [
        "llm_call_0000000000000001",
        "llm_call_0000000000000003",
    ]
    assert store.list_for_run("run_missing") == []
    db.close()


def test_duplicate_id_raises_typed_error_and_leaves_one_row(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "sessions.db")
    store = Store(db)
    store.append(record(1))

    with pytest.raises(CallLogAlreadyExistsError) as excinfo:
        store.append(record(1, outcome="fail", reason_code=LlmReasonCode.CALL_FAILED))

    assert excinfo.value.llm_call_log_id == "llm_call_0000000000000001"
    (stored,) = store.list_all()
    assert stored.validation_outcome == "pass"
    db.close()


def test_reads_revalidate_through_the_contract(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "sessions.db")
    store = Store(db)
    store.append(record(1))
    with db.transaction() as cursor:
        cursor.execute(
            "UPDATE llm_call_logs SET payload = ?",
            ('{"llm_call_log_id": "llm_call_0000000000000001"}',),
        )

    with pytest.raises(ValueError):
        store.list_all()
    db.close()


def test_schema_version_is_recorded(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "sessions.db")
    Store(db)

    with db.read() as cursor:
        cursor.execute("SELECT version FROM schema_version WHERE component = ?", (COMPONENT,))
        assert cursor.fetchone() == (SCHEMA_VERSION,)
    db.close()


def test_construction_is_idempotent_across_stores(tmp_path: Path) -> None:
    db = SqliteDatabase(tmp_path / "sessions.db")
    first = Store(db)
    first.append(record(1))
    second = Store(db)

    assert len(second.list_all()) == 1
    db.close()
