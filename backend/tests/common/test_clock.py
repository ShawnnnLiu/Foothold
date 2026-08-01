from datetime import UTC, datetime, timedelta

from starmap.common.clock import Clock, SystemClock
from tests.support.clocks import FrozenClock


def test_system_clock_now_is_timezone_aware_utc() -> None:
    now = SystemClock().now()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)


def test_system_clock_monotonic_is_non_decreasing() -> None:
    clock = SystemClock()
    first = clock.monotonic()
    second = clock.monotonic()
    assert second >= first


def test_implementations_satisfy_protocol() -> None:
    assert isinstance(SystemClock(), Clock)
    assert isinstance(FrozenClock(datetime(2026, 7, 31, tzinfo=UTC)), Clock)


def test_frozen_clock_is_frozen_until_advanced() -> None:
    start = datetime(2026, 7, 31, 12, 0, 0, tzinfo=UTC)
    clock = FrozenClock(start)
    assert clock.now() == start
    assert clock.now() == start
    assert clock.monotonic() == 0.0

    clock.advance(90)
    assert clock.now() == start + timedelta(seconds=90)
    assert clock.monotonic() == 90.0
