"""Shared seams for the engine tests: frozen clock, sequential ids, real SQLite.

The call log is never faked; every engine test writes through the real
`SqliteCallLogStore` against an in-memory database with the real schema.
"""

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from pydantic import BaseModel, Field, model_validator

from starmap.common.sqlite import SqliteDatabase
from starmap.contracts.base import FROZEN
from starmap.llm.call_log import SqliteCallLogStore
from starmap.llm.engine import AdapterConfig, GenerationEngine
from tests.support.clocks import FrozenClock
from tests.support.ids import SequentialIdGenerator
from tests.support.sleepers import RecordingSleeper
from tests.support.transports import FakeTransport

START = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)
RUN_ID = "run_test"
SYSTEM = "You are a deterministic test node."
USER_PROMPT = "Classify the sample."


class Answer(BaseModel):
    """Toy output contract.

    The cross-field validator is what makes the boundary-revalidation test
    possible: a payload can satisfy the wire schema and still fail here.
    """

    model_config = FROZEN

    label: str = Field(min_length=1)
    score: int = Field(ge=0, le=10)
    note: str | None = None

    @model_validator(mode="after")
    def _check_high_label_needs_high_score(self) -> "Answer":
        if self.label == "high" and self.score < 5:
            raise ValueError(f"label 'high' requires score >= 5, got {self.score}")
        return self


VALID_PAYLOAD = {"label": "low", "score": 2, "note": None}
CROSS_FIELD_INVALID_PAYLOAD = {"label": "high", "score": 1, "note": None}

CONFIG = AdapterConfig(
    model_name="claude-sonnet-5",
    prompt_version="test-node-v1",
    max_tokens=2000,
    input_price_per_mtok=3.00,
    output_price_per_mtok=15.00,
)


class Harness:
    """Everything an engine test needs, wired to deterministic twins."""

    def __init__(self, db: SqliteDatabase) -> None:
        self.clock = FrozenClock(START)
        self.ids = SequentialIdGenerator()
        self.sleeper = RecordingSleeper()
        self.store = SqliteCallLogStore(db)
        self.raw_sink: list[str] = []
        self.recorded: list[str] = []

    def engine(
        self,
        transport: FakeTransport,
        *,
        config: AdapterConfig = CONFIG,
        node_name: str = "transcript_parser",
    ) -> GenerationEngine[Answer]:
        return GenerationEngine(
            node_name,
            Answer,
            config,
            transport,
            self.store,
            self.clock,
            self.ids,
            self.raw_sink.append,
            self.sleeper,
            lambda record: self.recorded.append(record.llm_call_log_id),
        )

    def rows(self) -> list[tuple[int, int, str, str | None]]:
        return [
            (
                row.attempt,
                row.sdk_retry,
                row.validation_outcome,
                None if row.reason_code is None else row.reason_code.value,
            )
            for row in self.store.list_for_run(RUN_ID)
        ]


@pytest.fixture
def harness() -> Iterator[Harness]:
    db = SqliteDatabase(":memory:")
    try:
        yield Harness(db)
    finally:
        db.close()
