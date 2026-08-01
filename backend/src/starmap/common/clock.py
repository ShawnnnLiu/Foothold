"""Clock protocol and the production system clock.

The test twin `FrozenClock` lives in `backend/tests/support/clocks.py`.
"""

import time
from datetime import UTC, datetime
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    def now(self) -> datetime:
        """Current wall-clock time, always timezone-aware UTC."""
        ...

    def monotonic(self) -> float:
        """Monotonic seconds for measuring durations."""
        ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def monotonic(self) -> float:
        return time.monotonic()
