"""Error bodies, the 409 precondition set, and the handler registrations.

The TR 4.4 trap is binding here: pydantic's `ValidationError` IS a
`ValueError` subclass, so the 422 handler must be registered explicitly or
every contract violation would surface as a 400. Starlette resolves handlers
by walking the exception's MRO, so the explicit registration is what makes
"most-specific first" hold.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from starmap.common.errors import StarmapError
from starmap.retrieval.errors import Fts5UnavailableError, InstitutionNotIndexedError


class UnknownAgreementError(StarmapError):
    """No agreement with the requested key exists for the pair."""

    def __init__(self, sending: int, receiving: int, major_key: str) -> None:
        super().__init__(
            f"no agreement with key {major_key!r} exists for pair {sending} -> {receiving}",
            reason_code="unknown_agreement",
        )


class LlmUnavailableError(StarmapError):
    """The app was built without a transport, so the LLM surface is disabled."""

    def __init__(self) -> None:
        super().__init__(
            "LLM features are disabled: no transport is configured (set ANTHROPIC_API_KEY)",
            reason_code="llm_unavailable",
        )


# `StarmapError` subclasses carrying a precondition semantic (doc 01): the
# request was well-formed but the world it names does not exist, so 409.
# The free-form `reason_code` strings follow the `unknown_agreement` precedent.
PRECONDITION_ERRORS: tuple[type[StarmapError], ...] = (
    InstitutionNotIndexedError,
    Fts5UnavailableError,
    UnknownAgreementError,
    LlmUnavailableError,
)


def error_body(error: str, type: str, reason_code: str | None = None) -> dict[str, str | None]:
    return {"error": error, "type": type, "reason_code": reason_code}


def _validation_message(exc: RequestValidationError | ValidationError) -> str:
    return "; ".join(str(entry["msg"]) for entry in exc.errors()) or "invalid request"


def register_exception_handlers(app: FastAPI) -> None:
    """Most-specific first: precondition = 409, StarmapError = 400,
    ValidationError = 422, ValueError = 400."""

    async def precondition(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarmapError)
        return JSONResponse(
            status_code=409,
            content=error_body(exc.message, "precondition_failed", exc.reason_code),
        )

    async def starmap_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarmapError)
        return JSONResponse(
            status_code=400, content=error_body(exc.message, "bad_request", exc.reason_code)
        )

    async def validation_error(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError | ValidationError)
        return JSONResponse(
            status_code=422, content=error_body(_validation_message(exc), "validation_error")
        )

    async def value_error(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=400, content=error_body(str(exc), "value_error"))

    for precondition_type in PRECONDITION_ERRORS:
        app.add_exception_handler(precondition_type, precondition)
    app.add_exception_handler(StarmapError, starmap_error)
    app.add_exception_handler(RequestValidationError, validation_error)
    app.add_exception_handler(ValidationError, validation_error)
    app.add_exception_handler(ValueError, value_error)
