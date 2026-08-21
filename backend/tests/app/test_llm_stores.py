"""The two LLM job stores (doc 03): round-trips, the uniform-404 seam, and
the pending-TTL rule, all against a real in-memory SQLite with the real
schema triples."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from starmap.app.web.store import (
    PENDING_TTL_SECONDS,
    PetitionStore,
    TranscriptParseStore,
    selection_key,
)
from starmap.common.sqlite import SqliteDatabase
from starmap.contracts.petition import CitedCourse, Petition
from starmap.contracts.reason_codes import LlmReasonCode
from starmap.contracts.transcript_parse import TranscriptChip, TranscriptParse

NOW = datetime(2026, 8, 3, 12, 0, 0, tzinfo=UTC)
SID = "sid_00000000000000000000000000000001"
OTHER_SID = "sid_00000000000000000000000000000002"
PARSE_ID = "parse_0123456789abcdef"
PETITION_ID = "pet_0123456789abcdef"
EVALUATION_ID = "eval_0123456789abcdef"
POSITIONS = [1, 3, 7]
KEY = selection_key(POSITIONS)

CHIP = TranscriptChip(
    course_code="MATH 1A",
    title="Calculus I",
    units_min=5.0,
    units_max=5.0,
    resolution="exact",
)


@pytest.fixture
def db() -> Iterator[SqliteDatabase]:
    database = SqliteDatabase(":memory:")
    try:
        yield database
    finally:
        database.close()


@pytest.fixture
def parses(db: SqliteDatabase) -> TranscriptParseStore:
    return TranscriptParseStore(db)


@pytest.fixture
def petitions(db: SqliteDatabase) -> PetitionStore:
    return PetitionStore(db)


def pending_parse() -> TranscriptParse:
    return TranscriptParse(
        parse_id=PARSE_ID,
        sending_institution_id=113,
        status="pending",
        created_at=NOW,
    )


def pending_petition(created_at: datetime = NOW) -> Petition:
    return Petition(
        petition_id=PETITION_ID,
        evaluation_id=EVALUATION_ID,
        finding_positions=POSITIONS,
        status="pending",
        created_at=created_at,
    )


def finished_petition() -> Petition:
    return Petition(
        petition_id=PETITION_ID,
        evaluation_id=EVALUATION_ID,
        finding_positions=POSITIONS,
        status="failed",
        reason_code=LlmReasonCode.AUTH_FAILED,
        created_at=NOW,
    )


# --- selection key -----------------------------------------------------------


def test_selection_key_is_order_insensitive() -> None:
    assert selection_key([7, 1, 3]) == "1,3,7"
    assert selection_key([7, 1, 3]) == selection_key(POSITIONS)


# --- transcript parses -------------------------------------------------------


def test_parse_put_finish_get_round_trips_through_the_contract(
    parses: TranscriptParseStore,
) -> None:
    parses.put(SID, pending_parse())
    assert parses.get(SID, PARSE_ID) == pending_parse()

    finished = TranscriptParse(
        parse_id=PARSE_ID,
        sending_institution_id=113,
        status="succeeded",
        chips=[CHIP],
        unresolved=[],
        created_at=NOW,
    )
    parses.finish(finished)
    assert parses.get(SID, PARSE_ID) == finished


def test_parse_get_is_none_for_unknown_and_cross_session_ids(
    parses: TranscriptParseStore,
) -> None:
    parses.put(SID, pending_parse())

    assert parses.get(SID, "parse_ffffffffffffffff") is None
    assert parses.get(OTHER_SID, PARSE_ID) is None


def test_parse_duplicate_insert_raises(parses: TranscriptParseStore) -> None:
    parses.put(SID, pending_parse())

    with pytest.raises(sqlite3.IntegrityError):
        parses.put(SID, pending_parse())


# --- petitions ---------------------------------------------------------------


def test_petition_put_finish_get_round_trips_through_the_contract(
    petitions: PetitionStore,
) -> None:
    petitions.put(SID, pending_petition())
    assert petitions.get(SID, PETITION_ID) == pending_petition()

    finished = Petition(
        petition_id=PETITION_ID,
        evaluation_id=EVALUATION_ID,
        finding_positions=POSITIONS,
        status="succeeded",
        letter_text="x" * 200,
        cited=[CitedCourse(course_code="MATH 1A", finding_position=1)],
        created_at=NOW,
    )
    petitions.finish(finished)
    assert petitions.get(SID, PETITION_ID) == finished


def test_petition_get_is_none_for_unknown_and_cross_session_ids(
    petitions: PetitionStore,
) -> None:
    petitions.put(SID, pending_petition())

    assert petitions.get(SID, "pet_ffffffffffffffff") is None
    assert petitions.get(OTHER_SID, PETITION_ID) is None


def test_petition_duplicate_insert_raises(petitions: PetitionStore) -> None:
    petitions.put(SID, pending_petition())

    with pytest.raises(sqlite3.IntegrityError):
        petitions.put(SID, pending_petition())


# --- the pending-TTL rule ----------------------------------------------------


def test_pending_petition_id_inside_the_ttl(petitions: PetitionStore) -> None:
    petitions.put(SID, pending_petition())

    just_before_expiry = NOW + timedelta(seconds=PENDING_TTL_SECONDS - 1)
    assert (
        petitions.pending_petition_id(SID, EVALUATION_ID, KEY, now=just_before_expiry)
        == PETITION_ID
    )


def test_pending_row_at_the_ttl_is_abandoned(petitions: PetitionStore) -> None:
    petitions.put(SID, pending_petition())

    at_expiry = NOW + timedelta(seconds=PENDING_TTL_SECONDS)
    assert petitions.pending_petition_id(SID, EVALUATION_ID, KEY, now=at_expiry) is None


def test_pending_petition_id_is_none_once_finished(petitions: PetitionStore) -> None:
    petitions.put(SID, pending_petition())
    petitions.finish(finished_petition())

    assert petitions.pending_petition_id(SID, EVALUATION_ID, KEY, now=NOW) is None


def test_pending_petition_id_is_scoped_to_sid_evaluation_and_selection(
    petitions: PetitionStore,
) -> None:
    petitions.put(SID, pending_petition())

    assert petitions.pending_petition_id(OTHER_SID, EVALUATION_ID, KEY, now=NOW) is None
    assert petitions.pending_petition_id(SID, "eval_ffffffffffffffff", KEY, now=NOW) is None
    assert petitions.pending_petition_id(SID, EVALUATION_ID, selection_key([1, 3]), now=NOW) is None
