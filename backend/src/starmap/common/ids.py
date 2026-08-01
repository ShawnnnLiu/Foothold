"""Random id generation and the single hash helper.

Content-derived ids (doc/snapshot/chunk/requirement-group) are NOT here;
they live beside their owning regions with their derivation formulas.

The test twin `SequentialIdGenerator` lives in `backend/tests/support/ids.py`.
"""

import hashlib
from typing import Protocol, runtime_checkable
from uuid import uuid4


@runtime_checkable
class IdGenerator(Protocol):
    def new_id(self, prefix: str) -> str:
        """A fresh id of the form `{prefix}_{16 hex chars}`."""
        ...


class UuidIdGenerator:
    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid4().hex[:16]}"


def sha256_hex(text: str) -> str:
    """The single hash helper the whole repo uses."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
