"""Deterministic clock twin for tests."""

from datetime import datetime, timedelta


class FrozenClock:
    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FrozenClock requires a timezone-aware start")
        self._now = start
        self._monotonic = 0.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._monotonic += seconds
