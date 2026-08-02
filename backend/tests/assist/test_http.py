"""`UrllibTransport` driven by a stub opener. Nothing here opens a socket.

The one behaviour worth pinning hard: `urllib` raises `HTTPError` on every
4xx/5xx, but ASSIST answers 400 as ordinary control flow (the session needs
refreshing). This transport must hand that back as data so `fetch.py` can act
on it, while a genuine `URLError` still propagates as a network failure.
"""

import io
import urllib.error
import urllib.request
from email.message import Message
from http.cookiejar import Cookie, CookieJar

import pytest

from starmap.assist.http import (
    TIMEOUT_SECONDS,
    HttpResponse,
    RawResponse,
    UrllibTransport,
    build_transport,
)

URL = "https://www.assist.org/api/institutions"


class StubRawResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body
        self.closed = False

    def read(self) -> bytes:
        return self._body

    def close(self) -> None:
        self.closed = True


class StubOpener:
    def __init__(self, result: RawResponse | Exception) -> None:
        self._result = result
        self.calls: list[tuple[urllib.request.Request, float]] = []

    def open(self, fullurl: urllib.request.Request, *, timeout: float) -> RawResponse:
        self.calls.append((fullurl, timeout))
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def http_error(code: int, body: bytes) -> urllib.error.HTTPError:
    return urllib.error.HTTPError(URL, code, "Bad Request", Message(), io.BytesIO(body))


def make_cookie(name: str, value: str) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain="www.assist.org",
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=False,
        comment=None,
        comment_url=None,
        rest={},
    )


def test_a_200_becomes_an_http_response_and_the_body_is_closed() -> None:
    response = StubRawResponse(200, b'{"ok": true}')
    transport = UrllibTransport(StubOpener(response), CookieJar())

    assert transport.get(URL, {"Accept": "application/json"}) == HttpResponse(
        status=200, body=b'{"ok": true}'
    )
    assert response.closed


def test_the_request_carries_the_headers_and_the_timeout() -> None:
    opener = StubOpener(StubRawResponse(200, b"[]"))
    transport = UrllibTransport(opener, CookieJar())

    transport.get(URL, {"User-Agent": "test-agent", "X-XSRF-TOKEN": "abc"})

    request, timeout = opener.calls[0]
    assert request.full_url == URL
    assert request.get_header("User-agent") == "test-agent"
    assert request.get_header("X-xsrf-token") == "abc"
    assert timeout == TIMEOUT_SECONDS


def test_a_400_comes_back_as_data_not_as_an_exception() -> None:
    transport = UrllibTransport(StubOpener(http_error(400, b'{"code":400}')), CookieJar())

    assert transport.get(URL, {}) == HttpResponse(status=400, body=b'{"code":400}')


def test_a_500_comes_back_as_data_too() -> None:
    transport = UrllibTransport(StubOpener(http_error(500, b"boom")), CookieJar())

    assert transport.get(URL, {}).status == 500


def test_a_network_failure_propagates() -> None:
    transport = UrllibTransport(StubOpener(urllib.error.URLError("no route")), CookieJar())

    with pytest.raises(urllib.error.URLError):
        transport.get(URL, {})


def test_cookie_value_reads_the_jar_and_returns_none_when_absent() -> None:
    jar = CookieJar()
    jar.set_cookie(make_cookie("X-XSRF-TOKEN", "token-value"))
    transport = UrllibTransport(StubOpener(StubRawResponse(200, b"[]")), jar)

    assert transport.cookie_value("X-XSRF-TOKEN") == "token-value"
    assert transport.cookie_value("nope") is None


def test_the_production_transport_starts_with_an_empty_session() -> None:
    """`build_transport` wires a fresh jar; constructing it touches no network."""
    assert build_transport().cookie_value("X-XSRF-TOKEN") is None


def test_a_custom_timeout_is_honoured() -> None:
    opener = StubOpener(StubRawResponse(200, b"[]"))
    UrllibTransport(opener, CookieJar(), timeout_seconds=5.0).get(URL, {})

    assert opener.calls[0][1] == 5.0
