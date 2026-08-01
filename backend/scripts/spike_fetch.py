"""Day-1 spike fetcher (increment 1). SUPERSEDED by catalog/fetch.py in increment 3.

Throwaway script implementing exactly the cache format locked in
docs/week-1-implementations/01-day1-risk-spikes.md:

- File: data/raw/<sha256(url).hexdigest()>.html, raw response bytes decoded
  with the declared charset or UTF-8 with replacement.
- Ledger: one JSON line appended to data/raw/manifest.jsonl per successful
  fetch: {"url": ..., "sha256": ..., "date_fetched": "YYYY-MM-DD", "status": 200}.
- Politeness: 1 req/s, 20 s timeout, fixed UA.

Usage: uv run python scripts/spike_fetch.py <url> [<url> ...]
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
MANIFEST = RAW_DIR / "manifest.jsonl"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
TIMEOUT_S = 20
DELAY_S = 1.0


def fetch_one(url: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_S) as response:
        status = response.status
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    text = raw.decode(charset, errors="replace")
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    out_path = RAW_DIR / f"{digest}.html"
    out_path.write_text(text, encoding="utf-8")
    line = {
        "url": url,
        "sha256": digest,
        "date_fetched": date.today().isoformat(),
        "status": status,
    }
    with MANIFEST.open("a", encoding="utf-8") as ledger:
        ledger.write(json.dumps(line) + "\n")
    print(f"{status} {len(raw):>8}B {digest[:12]}... {url}")


def main(urls: list[str]) -> int:
    if not urls:
        print("usage: spike_fetch.py <url> [<url> ...]", file=sys.stderr)
        return 2
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for i, url in enumerate(urls):
        if i > 0:
            time.sleep(DELAY_S)
        try:
            fetch_one(url)
        except Exception as exc:  # spike: record and continue, never abort the batch
            print(f"FAIL {url}: {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
