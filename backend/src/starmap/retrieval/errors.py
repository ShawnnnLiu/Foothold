"""Typed errors for the retrieval region (implementation plan doc 04).

`Fts5UnavailableError` policy (TR 1.6, transplanted): raised at index
CONSTRUCTION by a cheap in-memory FTS5 probe, before any query can run, and
NEVER caught to degrade. A silent fallback would quietly serve a different
ranking in some environments, which is exactly what the deterministic
retrieval axiom forbids.
"""

from starmap.common.errors import StarmapError
from starmap.contracts.reason_codes import RetrievalCode


class RetrievalError(StarmapError):
    """Base class for every typed error raised inside the retrieval region."""


class Fts5UnavailableError(RetrievalError):
    """The linked SQLite build lacks FTS5."""

    def __init__(self) -> None:
        super().__init__(
            "this SQLite build lacks FTS5 support; retrieval cannot run",
            reason_code=RetrievalCode.FTS5_UNAVAILABLE,
        )


class InstitutionNotIndexedError(RetrievalError):
    """A search was issued against an institution with no built index."""

    def __init__(self, institution_id: int) -> None:
        super().__init__(
            f"institution {institution_id} has no built course index",
            reason_code=RetrievalCode.INSTITUTION_NOT_INDEXED,
        )
        self.institution_id = institution_id
