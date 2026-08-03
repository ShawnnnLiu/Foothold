"""The `sid` session middleware (doc 01, "Session middleware").

The trust boundary: identity is ONLY this cookie. The middleware derives
`request.state.sid` on every request and no route may accept a user or
session id from the body or headers. A well-formed unknown sid is accepted
as-is; it owns no evaluations, so it can read nothing.
"""

import re

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from starmap.common.ids import IdGenerator

SID_COOKIE = "sid"
SID_PATTERN = re.compile(r"^sid_[0-9a-f]+$")


class SidMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, *, ids: IdGenerator, secure: bool) -> None:
        super().__init__(app)
        self._ids = ids
        self._secure = secure

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        cookie = request.cookies.get(SID_COOKIE)
        if cookie is not None and SID_PATTERN.fullmatch(cookie):
            sid, minted = cookie, False
        else:
            sid, minted = self._ids.new_id(SID_COOKIE), True
        request.state.sid = sid
        response = await call_next(request)
        if minted:
            response.set_cookie(
                SID_COOKIE,
                sid,
                httponly=True,
                samesite="lax",
                path="/",
                secure=self._secure,
            )
        return response
