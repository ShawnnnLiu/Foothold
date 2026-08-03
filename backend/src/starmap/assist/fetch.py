"""The polite, cached ASSIST fetcher (implementation plan doc 02).

`AssistFetcher` knows how to get JSON out of ASSIST politely and reproducibly.
It deliberately knows nothing about WHICH urls the corridor needs: that is
`corridor.py`, which builds urls and hands them here.

Four behaviours, all locked by doc 02:

- Session bootstrap. Bare `api/*` requests answer 400. The SPA's anti-forgery
  pair is required: `GET /` fills the cookie jar with a non-HttpOnly
  `X-XSRF-TOKEN` cookie whose value every API request echoes as a header. The
  bootstrap is lazy (nothing happens until the first cache miss) and a 400 mid
  run re-bootstraps exactly ONCE and retries the request once.
- Session quota. ASSIST meters requests PER SESSION, not per unit time: the
  S9c pilot measured ~50-55 requests before every further request answered 429,
  and a fresh session succeeded immediately with no idle period, while the
  exhausted one stayed shut. So a bootstrap starts a NEW session (the jar is
  emptied first), the fetcher renews proactively every
  `SESSION_REQUEST_BUDGET` requests, and a 429 renews reactively up to
  `MAX_SESSION_RENEWALS` times before failing typed. Pacing is unchanged: this
  is about session identity, not about going faster.
- Politeness. At least `MIN_REQUEST_INTERVAL_SECONDS` between consecutive
  NETWORK requests, measured with `clock.monotonic()` and enforced through the
  injected sleeper. Cache hits neither sleep nor touch the network.
- The cache. `<cache_dir>/<sha256(url)[:16]>.json` holds the response body
  verbatim, and `manifest.jsonl` records one append-only line per `fetch_json`
  network outcome, INCLUDING failures, so a non-200 leaves a trace rather than
  vanishing. The bootstrap `GET /` is session plumbing rather than a fetched
  payload and is not recorded. Both files live under gitignored
  `data/raw/assist/`.
- Offline. The DEFAULT. A cache miss raises typed instead of reaching the
  network, which is how the test suite and `make build-data` run. Network
  access is opt-in exactly once, at the S9c permission gate.

Every failure out of this module is an `AssistFetchError` carrying
`session_bootstrap_failed` or `agreement_fetch_failed`; no raw `OSError`
escapes the region.
"""

import json
import time
from collections.abc import Callable
from pathlib import Path

from starmap.assist.errors import AssistFetchError
from starmap.assist.http import USER_AGENT, HttpResponse, HttpTransport
from starmap.common.clock import Clock
from starmap.common.ids import sha256_hex
from starmap.contracts.reason_codes import AssistBuildCode

MIN_REQUEST_INTERVAL_SECONDS = 1.0
XSRF_COOKIE_NAME = "X-XSRF-TOKEN"
MANIFEST_NAME = "manifest.jsonl"
CACHE_KEY_LENGTH = 16
SESSION_REFRESH_STATUS = 400
RATE_LIMIT_STATUS = 429

# Measured at the S9c permission gate against live ASSIST: one session served
# 55 requests and another 50 before answering 429 to everything after. 40 sits
# below the smaller observation with room to spare, so the corridor walk renews
# before it is refused rather than after, and ASSIST sees fewer rejected
# requests rather than more (politeness axiom).
SESSION_REQUEST_BUDGET = 40

# Bounded like every other repair in this codebase: a 429 that survives three
# fresh sessions is not a quota problem and must not become a retry storm.
MAX_SESSION_RENEWALS = 3


def cache_key(url: str) -> str:
    """The cache filename stem for a url: a truncated sha256 of the url itself."""
    return sha256_hex(url)[:CACHE_KEY_LENGTH]


class AssistFetcher:
    def __init__(
        self,
        transport: HttpTransport,
        cache_dir: Path,
        clock: Clock,
        sleeper: Callable[[float], None] = time.sleep,
        *,
        root_url: str,
        offline: bool = True,
    ) -> None:
        self._transport = transport
        self._cache_dir = cache_dir
        self._clock = clock
        self._sleeper = sleeper
        self._root_url = root_url
        self._offline = offline
        self._token: str | None = None
        self._last_request_monotonic: float | None = None
        self._session_requests = 0

    def fetch_json(self, url: str) -> object:
        """The single entry point: cached JSON for `url`, or a typed failure."""
        path = self.cache_path(url)
        if path.exists():
            return self._decode(url, path.read_bytes())
        if self._offline:
            raise AssistFetchError(
                f"offline mode: no cached ASSIST response for {url}",
                reason_code=AssistBuildCode.AGREEMENT_FETCH_FAILED,
            )
        response = self._get_with_session_refresh(url)
        if response.status != 200:
            self._append_manifest(url, response.status)
            raise AssistFetchError(
                f"ASSIST request failed with HTTP {response.status}: {url}",
                reason_code=AssistBuildCode.AGREEMENT_FETCH_FAILED,
            )
        self._write_cache(path, response.body)
        self._append_manifest(url, response.status)
        return self._decode(url, response.body)

    def cache_path(self, url: str) -> Path:
        return self._cache_dir / f"{cache_key(url)}.json"

    @property
    def manifest_path(self) -> Path:
        return self._cache_dir / MANIFEST_NAME

    def _get_with_session_refresh(self, url: str) -> HttpResponse:
        """One API request, with both locked session rules.

        A 400 means the anti-forgery pair went stale: re-bootstrap once, retry
        once. A 429 means this session spent its quota: renew and retry, up to
        `MAX_SESSION_RENEWALS`. The 400 retry feeds into the 429 rule, since a
        refreshed session can still turn out to be an exhausted one.
        """
        if self._token is None or self._session_requests >= SESSION_REQUEST_BUDGET:
            self._bootstrap()
        response = self._api_request(url)
        if response.status == SESSION_REFRESH_STATUS:
            self._bootstrap()
            response = self._api_request(url)
        for _ in range(MAX_SESSION_RENEWALS):
            if response.status != RATE_LIMIT_STATUS:
                break
            self._bootstrap()
            response = self._api_request(url)
        return response

    def _api_request(self, url: str) -> HttpResponse:
        """One metered API call: everything ASSIST counts against the session."""
        self._session_requests += 1
        return self._request(
            url, self._api_headers(), reason_code=AssistBuildCode.AGREEMENT_FETCH_FAILED
        )

    def _bootstrap(self) -> None:
        """Start a NEW session: empty the jar, `GET /` to refill it, capture the token.

        Emptying first is what makes this a renewal rather than a refresh.
        ASSIST meters per session, so carrying the old cookies forward would
        inherit the exhausted quota and every retry would answer 429 again.
        """
        self._transport.clear_cookies()
        self._token = None
        self._session_requests = 0
        response = self._request(
            self._root_url,
            {"User-Agent": USER_AGENT},
            reason_code=AssistBuildCode.SESSION_BOOTSTRAP_FAILED,
        )
        if response.status != 200:
            raise AssistFetchError(
                f"ASSIST session bootstrap failed with HTTP {response.status}: {self._root_url}",
                reason_code=AssistBuildCode.SESSION_BOOTSTRAP_FAILED,
            )
        token = self._transport.cookie_value(XSRF_COOKIE_NAME)
        if not token:
            raise AssistFetchError(
                f"ASSIST session bootstrap set no {XSRF_COOKIE_NAME} cookie: {self._root_url}",
                reason_code=AssistBuildCode.SESSION_BOOTSTRAP_FAILED,
            )
        self._token = token

    def _api_headers(self) -> dict[str, str]:
        token = self._token
        assert token is not None, "_api_headers called before the session was bootstrapped"
        return {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            XSRF_COOKIE_NAME: token,
        }

    def _request(
        self, url: str, headers: dict[str, str], *, reason_code: AssistBuildCode
    ) -> HttpResponse:
        """Every network request in this module goes through here, paced."""
        self._pace()
        try:
            response = self._transport.get(url, headers)
        except OSError as error:
            raise AssistFetchError(
                f"ASSIST request raised {type(error).__name__}: {url}",
                reason_code=reason_code,
            ) from error
        self._last_request_monotonic = self._clock.monotonic()
        return response

    def _pace(self) -> None:
        last = self._last_request_monotonic
        if last is None:
            return
        elapsed = self._clock.monotonic() - last
        if elapsed < MIN_REQUEST_INTERVAL_SECONDS:
            self._sleeper(MIN_REQUEST_INTERVAL_SECONDS - elapsed)

    def _decode(self, url: str, body: bytes) -> object:
        try:
            return json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError) as error:
            raise AssistFetchError(
                f"ASSIST response was not valid JSON: {url}",
                reason_code=AssistBuildCode.AGREEMENT_FETCH_FAILED,
            ) from error

    def _write_cache(self, path: Path, body: bytes) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)

    def _append_manifest(self, url: str, status: int) -> None:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "url": url,
                "key": cache_key(url),
                "status": status,
                "fetched_at": self._clock.now().isoformat(),
            },
            sort_keys=True,
        )
        with self.manifest_path.open("a", encoding="utf-8") as manifest:
            manifest.write(line + "\n")
