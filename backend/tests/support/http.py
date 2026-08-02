"""FakeHttpTransport: the whole ASSIST network testing seam.

Fakes are allowed at external boundaries only (testing strategy, "Hard Rules"),
and this is that boundary: nothing below it is faked, so the session bootstrap,
the 400 refresh rule, the pacing, the cache, and the manifest are all real code
under test.

A response value that is an `Exception` is RAISED, which is how network failure
is scripted. A value that is a LIST is consumed left to right and asserts when
exhausted, which is how a sequence like "400, then 200 after the re-bootstrap"
is expressed; a bare value answers its url unlimited times. There is no default
response: an unscripted url is a loud test failure, not a silent empty answer.

`cookies` is mutable so a test can script an absent `X-XSRF-TOKEN`, and
`requests` records `(url, headers)` per call, which is what proves the header
echo and the exact re-bootstrap request order.
"""

import json
from collections.abc import Mapping
from typing import Any

from starmap.assist.http import HttpResponse


def json_ok(payload: Any) -> HttpResponse:
    return HttpResponse(status=200, body=json.dumps(payload).encode("utf-8"))


def status(code: int, body: bytes = b"") -> HttpResponse:
    return HttpResponse(status=code, body=body)


def raw(body: bytes, *, code: int = 200) -> HttpResponse:
    return HttpResponse(status=code, body=body)


class FakeHttpTransport:
    def __init__(
        self,
        responses: Mapping[str, HttpResponse | Exception | list[HttpResponse | Exception]],
        cookies: dict[str, str] | None = None,
    ) -> None:
        self._responses = {
            url: list(value) if isinstance(value, list) else value
            for url, value in responses.items()
        }
        self.cookies = cookies if cookies is not None else {}
        self.requests: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, headers: dict[str, str]) -> HttpResponse:
        self.requests.append((url, dict(headers)))
        assert url in self._responses, f"FakeHttpTransport has no scripted response for {url}"
        scripted = self._responses[url]
        if isinstance(scripted, list):
            assert scripted, f"FakeHttpTransport script exhausted for {url}: an extra call was made"
            scripted = scripted.pop(0)
        if isinstance(scripted, Exception):
            raise scripted
        return scripted

    def cookie_value(self, name: str) -> str | None:
        return self.cookies.get(name)

    @property
    def urls(self) -> list[str]:
        return [url for url, _ in self.requests]
