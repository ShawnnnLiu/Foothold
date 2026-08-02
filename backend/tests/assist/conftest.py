"""Shared seams for the ASSIST fetcher tests.

Zero network, by construction: every fetcher here is wired to a scripted
`FakeHttpTransport`, a `FrozenClock`, and a `RecordingSleeper`, and the cache is
a real directory under `tmp_path` (SQLite and the filesystem are never faked).

The harness builds fetchers with `offline=False` because most tests are about
what the fetcher does when it DOES reach the transport; production defaults the
other way, and the offline tests pass the flag explicitly.
"""

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path

import pytest

from starmap.assist.corridor import ROOT_URL
from starmap.assist.fetch import XSRF_COOKIE_NAME, AssistFetcher
from starmap.assist.http import HttpResponse
from tests.support.clocks import FrozenClock
from tests.support.http import FakeHttpTransport, raw
from tests.support.sleepers import RecordingSleeper

START = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)
XSRF_TOKEN = "xsrf-token-for-tests"
BOOTSTRAP_BODY = b"<html>the assist SPA shell</html>"

Scripted = HttpResponse | Exception | list[HttpResponse | Exception]
Script = dict[str, Scripted]


class Harness:
    """Everything an ASSIST fetch test needs, wired to deterministic twins."""

    def __init__(self, cache_dir: Path) -> None:
        self.clock = FrozenClock(START)
        self.sleeper = RecordingSleeper()
        self.cache_dir = cache_dir

    def transport(
        self, responses: Mapping[str, Scripted], *, cookies: dict[str, str] | None = None
    ) -> FakeHttpTransport:
        """Script `responses`, adding a working bootstrap unless one is given."""
        scripted: Script = dict(responses)
        scripted.setdefault(ROOT_URL, raw(BOOTSTRAP_BODY))
        return FakeHttpTransport(
            scripted, {XSRF_COOKIE_NAME: XSRF_TOKEN} if cookies is None else cookies
        )

    def fetcher(self, transport: FakeHttpTransport, *, offline: bool = False) -> AssistFetcher:
        return AssistFetcher(
            transport,
            self.cache_dir,
            self.clock,
            self.sleeper,
            root_url=ROOT_URL,
            offline=offline,
        )

    def manifest_lines(self) -> list[dict[str, object]]:
        path = self.cache_dir / "manifest.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path / "assist")
