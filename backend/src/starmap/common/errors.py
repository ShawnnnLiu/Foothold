"""Typed error base for the whole repository.

Every typed error in the repo derives from `StarmapError`; no raw exception
crosses a region boundary. Region-specific error classes live in their own
regions and subclass this.
"""


class StarmapError(Exception):
    """Base class for every typed Starmap error."""

    def __init__(self, message: str, *, reason_code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.reason_code = reason_code
