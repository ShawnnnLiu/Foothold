"""Typed errors for the ASSIST region (implementation plan doc 02).

Three classes, and one rule about what they may say:

- `AssistError` is the region base; nothing raw crosses out of `assist/`.
- `AssistFetchError` covers network and session failures and always carries
  `session_bootstrap_failed` or `agreement_fetch_failed`.
- `AssistNormalizeError` covers per-agreement normalization failures. It is
  always caught by the per-agreement isolation loop and recorded as an
  exclusion; it never propagates out of the normalize stage.

Messages carry URLs, HTTP statuses, and exception TYPE NAMES only. They never
carry response bodies and never carry the `X-XSRF-TOKEN` value: a body can
quote request content, and the token is a session credential. This mirrors the
same rule in `llm/errors.py`.
"""

from starmap.common.errors import StarmapError
from starmap.contracts.reason_codes import AssistBuildCode


class AssistError(StarmapError):
    """Base class for every typed error raised inside the ASSIST region."""


class AssistFetchError(AssistError):
    """A session bootstrap or an agreement fetch failed."""

    def __init__(self, message: str, *, reason_code: AssistBuildCode) -> None:
        super().__init__(message, reason_code=reason_code)
        self.assist_reason_code = reason_code


class AssistNormalizeError(AssistError):
    """One agreement (or one articulation inside it) could not be normalized."""

    def __init__(self, message: str, *, reason_code: AssistBuildCode) -> None:
        super().__init__(message, reason_code=reason_code)
        self.assist_reason_code = reason_code
