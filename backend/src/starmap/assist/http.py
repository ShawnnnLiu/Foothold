"""The ASSIST network boundary (implementation plan doc 02).

This is the ONLY module in `src/` that touches `urllib.request`, and the
`HttpTransport` Protocol is the only seam the test suite fakes (testing
strategy, "Hard Rules": fakes are allowed at external boundaries only).

Three decisions worth stating:

1. A 400 is ASSIST control flow, not an exception. The API answers 400 whenever
   the anti-forgery pair is missing or stale, and `fetch.py` responds by
   re-bootstrapping the session. `urllib` raises `HTTPError` on every 4xx/5xx,
   so this transport translates that back into a plain `HttpResponse` carrying
   the status. Genuine network failures (`URLError`, `OSError`) propagate and
   are typed by the caller.
2. The cookie jar IS the session. It persists the `X-XSRF-TOKEN` cookie that
   every API request must echo as a header, so one jar lives for the life of
   one transport and `build_transport()` is the only thing that creates one.
3. A browser User-Agent is required: the spike confirmed the API refuses the
   default `urllib` agent.

The test twin `FakeHttpTransport` lives in `backend/tests/support/http.py`.
"""

import urllib.error
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from typing import Protocol

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes


class HttpTransport(Protocol):
    """The seam tests replace with `FakeHttpTransport`.

    `get` returns any HTTP status as data; it raises `OSError` (of which
    `urllib.error.URLError` is a subclass) only for a genuine network failure.
    `cookie_value` exposes the non-HttpOnly `X-XSRF-TOKEN` cookie so `fetch.py`
    can echo it as a header without knowing how the jar is stored.
    """

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse: ...

    def cookie_value(self, name: str) -> str | None: ...


class RawResponse(Protocol):
    """The subset of `http.client.HTTPResponse` this module uses."""

    status: int

    def read(self) -> bytes: ...

    def close(self) -> None: ...


class Opener(Protocol):
    """The `urllib` opener seam, narrowed to the one call this module makes."""

    def open(self, fullurl: urllib.request.Request, *, timeout: float) -> RawResponse: ...


class UrllibTransport:
    """Production transport over `urllib.request` with a shared cookie jar."""

    def __init__(
        self,
        opener: Opener,
        jar: CookieJar,
        *,
        timeout_seconds: float = TIMEOUT_SECONDS,
    ) -> None:
        self._opener = opener
        self._jar = jar
        self._timeout_seconds = timeout_seconds

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        request = urllib.request.Request(url, headers=headers)
        try:
            response = self._opener.open(request, timeout=self._timeout_seconds)
        except urllib.error.HTTPError as error:
            try:
                return HttpResponse(status=error.code, body=error.read())
            finally:
                error.close()
        try:
            return HttpResponse(status=response.status, body=response.read())
        finally:
            response.close()

    def cookie_value(self, name: str) -> str | None:
        for cookie in self._jar:
            if cookie.name == name:
                return cookie.value
        return None


def build_transport() -> UrllibTransport:
    """Production transport. No retries here: `fetch.py` owns the retry rule."""
    jar = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    return UrllibTransport(opener, jar)
