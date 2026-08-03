"""The ASSIST fetcher against a scripted transport. No network, ever.

Everything below the transport seam is real: the session bootstrap, the 400
refresh rule, the 429 session-renewal rule, the pacing arithmetic, the on-disk
cache, and the manifest.
"""

import json
import urllib.error

import pytest

from starmap.assist.corridor import ROOT_URL
from starmap.assist.errors import AssistFetchError
from starmap.assist.fetch import (
    MAX_SESSION_RENEWALS,
    SESSION_REQUEST_BUDGET,
    XSRF_COOKIE_NAME,
    cache_key,
)
from starmap.assist.http import USER_AGENT
from starmap.common.ids import sha256_hex
from starmap.contracts.reason_codes import AssistBuildCode
from tests.assist.conftest import START, XSRF_TOKEN, Harness
from tests.support.http import json_ok, raw, status

API_URL = "https://www.assist.org/api/institutions"
YEARS_URL = "https://www.assist.org/api/AcademicYears"
PAYLOAD = [{"id": 113, "isCommunityCollege": True}]


def test_bootstrap_echoes_the_token_and_sends_a_browser_agent(harness: Harness) -> None:
    transport = harness.transport({API_URL: json_ok(PAYLOAD)})

    assert harness.fetcher(transport).fetch_json(API_URL) == PAYLOAD

    assert transport.urls == [ROOT_URL, API_URL]
    assert transport.requests[0][1] == {"User-Agent": USER_AGENT}
    assert transport.requests[1][1] == {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        XSRF_COOKIE_NAME: XSRF_TOKEN,
    }


def test_a_missing_cookie_is_a_typed_bootstrap_failure(harness: Harness) -> None:
    transport = harness.transport({API_URL: json_ok(PAYLOAD)}, cookies={})

    with pytest.raises(AssistFetchError) as caught:
        harness.fetcher(transport).fetch_json(API_URL)

    assert caught.value.assist_reason_code is AssistBuildCode.SESSION_BOOTSTRAP_FAILED
    assert XSRF_COOKIE_NAME in caught.value.message
    assert transport.urls == [ROOT_URL]


def test_a_non_200_bootstrap_is_a_typed_bootstrap_failure(harness: Harness) -> None:
    transport = harness.transport({API_URL: json_ok(PAYLOAD), ROOT_URL: status(503)})

    with pytest.raises(AssistFetchError) as caught:
        harness.fetcher(transport).fetch_json(API_URL)

    assert caught.value.assist_reason_code is AssistBuildCode.SESSION_BOOTSTRAP_FAILED
    assert "503" in caught.value.message


def test_a_400_rebootstraps_exactly_once_and_retries_once(harness: Harness) -> None:
    transport = harness.transport({API_URL: [status(400), json_ok(PAYLOAD)]})

    assert harness.fetcher(transport).fetch_json(API_URL) == PAYLOAD

    assert transport.urls == [ROOT_URL, API_URL, ROOT_URL, API_URL]


def test_a_second_400_fails_typed_naming_the_url(harness: Harness) -> None:
    transport = harness.transport({API_URL: [status(400), status(400)]})

    with pytest.raises(AssistFetchError) as caught:
        harness.fetcher(transport).fetch_json(API_URL)

    assert caught.value.assist_reason_code is AssistBuildCode.AGREEMENT_FETCH_FAILED
    assert API_URL in caught.value.message
    # Exactly one re-bootstrap: no retry storm.
    assert transport.urls.count(ROOT_URL) == 2


def test_another_non_200_fails_typed_naming_url_and_status(harness: Harness) -> None:
    transport = harness.transport({API_URL: status(500)})

    with pytest.raises(AssistFetchError) as caught:
        harness.fetcher(transport).fetch_json(API_URL)

    assert caught.value.assist_reason_code is AssistBuildCode.AGREEMENT_FETCH_FAILED
    assert "500" in caught.value.message
    assert API_URL in caught.value.message
    # A 500 is not a session problem, so it never triggers a re-bootstrap.
    assert transport.urls.count(ROOT_URL) == 1


def test_a_429_renews_the_session_and_retries(harness: Harness) -> None:
    """ASSIST meters per session, so a 429 is answered with a NEW session.

    Measured live at the S9c gate: the exhausted session kept answering 429
    while a fresh one succeeded immediately with no idle period.
    """
    transport = harness.transport({API_URL: [status(429), json_ok(PAYLOAD)]})

    assert harness.fetcher(transport).fetch_json(API_URL) == PAYLOAD

    assert transport.urls == [ROOT_URL, API_URL, ROOT_URL, API_URL]
    # Two bootstraps, each of which emptied the jar first: a renewal, not a reuse.
    assert transport.clears == 2


def test_a_persistent_429_fails_typed_after_bounded_renewals(harness: Harness) -> None:
    """A 429 surviving fresh sessions is not a quota problem; it must not
    become a retry storm."""
    transport = harness.transport({API_URL: [status(429)] * (MAX_SESSION_RENEWALS + 1)})

    with pytest.raises(AssistFetchError) as caught:
        harness.fetcher(transport).fetch_json(API_URL)

    assert caught.value.assist_reason_code is AssistBuildCode.AGREEMENT_FETCH_FAILED
    assert "429" in caught.value.message
    assert API_URL in caught.value.message
    assert transport.urls.count(ROOT_URL) == 1 + MAX_SESSION_RENEWALS


def test_the_session_renews_before_the_quota_is_spent(harness: Harness) -> None:
    """Proactive renewal: the walk asks for a new session before ASSIST refuses
    the old one, so the corridor run spends requests on payloads rather than on
    rejections."""
    urls = [f"{API_URL}?page={index}" for index in range(SESSION_REQUEST_BUDGET + 1)]
    transport = harness.transport({url: json_ok(PAYLOAD) for url in urls})
    fetcher = harness.fetcher(transport)

    for url in urls:
        assert fetcher.fetch_json(url) == PAYLOAD

    # One bootstrap to start, one more when the budget ran out: no 429 needed.
    assert transport.urls.count(ROOT_URL) == 2
    assert transport.urls[-2:] == [ROOT_URL, urls[-1]]


def test_a_renewed_session_echoes_the_new_token(harness: Harness) -> None:
    """The jar is emptied before the re-bootstrap, so the token the fetcher
    echoes afterwards is the one the NEW session set."""
    transport = harness.transport({API_URL: [status(429), json_ok(PAYLOAD)]})

    harness.fetcher(transport).fetch_json(API_URL)

    assert transport.requests[-1][1][XSRF_COOKIE_NAME] == XSRF_TOKEN
    assert transport.cookies[XSRF_COOKIE_NAME] == XSRF_TOKEN


def test_a_non_json_body_fails_typed(harness: Harness) -> None:
    transport = harness.transport({API_URL: raw(b"<html>not json</html>")})

    with pytest.raises(AssistFetchError) as caught:
        harness.fetcher(transport).fetch_json(API_URL)

    assert caught.value.assist_reason_code is AssistBuildCode.AGREEMENT_FETCH_FAILED
    assert API_URL in caught.value.message


def test_a_network_error_is_typed_never_raw(harness: Harness) -> None:
    transport = harness.transport({API_URL: urllib.error.URLError("connection reset")})

    with pytest.raises(AssistFetchError) as caught:
        harness.fetcher(transport).fetch_json(API_URL)

    assert caught.value.assist_reason_code is AssistBuildCode.AGREEMENT_FETCH_FAILED
    assert "URLError" in caught.value.message
    assert isinstance(caught.value.__cause__, urllib.error.URLError)


def test_consecutive_network_requests_are_paced(harness: Harness) -> None:
    transport = harness.transport({API_URL: json_ok(PAYLOAD), YEARS_URL: json_ok([])})
    fetcher = harness.fetcher(transport)

    fetcher.fetch_json(API_URL)
    fetcher.fetch_json(YEARS_URL)

    # Three network requests (bootstrap, api, api) with a frozen monotonic
    # clock: the first takes no sleep, every later one pays the full second.
    assert harness.sleeper.durations == [1.0, 1.0]


def test_a_cache_hit_makes_no_request_and_no_sleep(harness: Harness) -> None:
    warm = harness.transport({API_URL: json_ok(PAYLOAD)})
    harness.fetcher(warm).fetch_json(API_URL)
    assert warm.urls == [ROOT_URL, API_URL]

    # A second run over the same cache directory, with its own sleeper.
    rerun = Harness(harness.cache_dir)
    reader = rerun.transport({})
    assert rerun.fetcher(reader).fetch_json(API_URL) == PAYLOAD

    assert reader.requests == []
    assert rerun.sleeper.durations == []


def test_offline_is_the_default_and_a_miss_fails_typed(harness: Harness) -> None:
    transport = harness.transport({API_URL: json_ok(PAYLOAD)})

    with pytest.raises(AssistFetchError) as caught:
        harness.fetcher(transport, offline=True).fetch_json(API_URL)

    assert caught.value.assist_reason_code is AssistBuildCode.AGREEMENT_FETCH_FAILED
    assert API_URL in caught.value.message
    assert transport.requests == []


def test_offline_still_serves_a_cache_hit(harness: Harness) -> None:
    harness.fetcher(harness.transport({API_URL: json_ok(PAYLOAD)})).fetch_json(API_URL)

    offline = harness.fetcher(harness.transport({}), offline=True)
    assert offline.fetch_json(API_URL) == PAYLOAD


def test_the_cache_path_is_the_truncated_url_hash_and_holds_bytes_verbatim(
    harness: Harness,
) -> None:
    body = json.dumps(PAYLOAD).encode("utf-8")
    harness.fetcher(harness.transport({API_URL: raw(body)})).fetch_json(API_URL)

    assert cache_key(API_URL) == sha256_hex(API_URL)[:16]
    assert (harness.cache_dir / f"{cache_key(API_URL)}.json").read_bytes() == body


def test_the_manifest_records_one_line_per_network_fetch(harness: Harness) -> None:
    fetcher = harness.fetcher(harness.transport({API_URL: json_ok(PAYLOAD)}))
    fetcher.fetch_json(API_URL)
    fetcher.fetch_json(API_URL)  # cache hit: adds nothing

    assert harness.manifest_lines() == [
        {
            "url": API_URL,
            "key": cache_key(API_URL),
            "status": 200,
            "fetched_at": START.isoformat(),
        }
    ]


def test_a_failed_fetch_leaves_a_manifest_trace_and_no_cache_file(harness: Harness) -> None:
    fetcher = harness.fetcher(harness.transport({API_URL: status(500)}))

    with pytest.raises(AssistFetchError):
        fetcher.fetch_json(API_URL)

    assert [line["status"] for line in harness.manifest_lines()] == [500]
    assert not (harness.cache_dir / f"{cache_key(API_URL)}.json").exists()


def test_error_messages_never_leak_the_token_or_the_body(harness: Harness) -> None:
    transport = harness.transport({API_URL: raw(b'{"secret": "do not echo me"}', code=500)})

    with pytest.raises(AssistFetchError) as caught:
        harness.fetcher(transport).fetch_json(API_URL)

    assert XSRF_TOKEN not in caught.value.message
    assert "do not echo me" not in caught.value.message
