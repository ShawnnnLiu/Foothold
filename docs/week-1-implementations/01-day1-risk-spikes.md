# Increment 1: Day-1 Risk Spikes (NETWORK)

Goal: retire the two external unknowns before anything is built on top of them.
Both spikes are network work: ask the user for go-ahead before the first request.
Findings land in `docs/notes/day1_spikes.md`; downstream docs (03, 07) consume its recorded decisions.

## Spike A: CULPA

The observed risk: `api.culpa.info` failed DNS resolution on 2026-07-30 (plan, "Top risks" 1).

Procedure, in order, recording every result verbatim into the findings doc:

1. DNS: `dig +short api.culpa.info` and `dig +short culpa.info`.
2. If DNS resolves, probe with a browser-like GET (stdlib urllib, 20 s timeout, fixed UA) against: `https://api.culpa.info/`, then any endpoint paths discovered in step 3.
   Record status codes and the first ~500 bytes of each body; never bulk-download.
3. Study `github.com/culpaonline` (WebFetch or browser): identify the API route definitions, the database schema (professors, courses, reviews, votes), whether reviews carry course associations, and whether any static data export exists in the org's repos.
4. Check `https://culpa.info` itself: if the site is alive but the API subdomain is dead, record whether the frontend calls a different API host (inspect network requests in the browser).

Decision matrix (record exactly one outcome):

| Outcome | Condition | Consequence for doc 07 |
|---|---|---|
| `as-planned` | API alive, endpoints as documented in the culpaonline repo, course associations present | Implement `catalog/culpa.py` against the documented endpoints |
| `adapted` | Alive but different host/shape | Record the real endpoints and payload shapes; doc 07's client section is rewritten against them before execution |
| `static-fallback` | API dead but a usable static export exists | Ingest the export file; record its URL, snapshot date, and license posture |
| `skip` | Nothing usable | `--skip-culpa` becomes the build default; cut-line 3 (drop review excerpts) is pre-applied; the NodeDrawer CULPA panel degrades to absent |

## Spike B: Bulletin selector pinning

Fetch, at 1 req/s with a 20 s timeout and fixed UA, into the real cache format (below):

1. The department index: `https://bulletin.columbia.edu/columbia-college/departments-instruction/` (verify this URL first; if it 404s, locate the index from `https://bulletin.columbia.edu/columbia-college/` and record the correction).
2. Five diverse department pages: Computer Science, Economics, English and Comparative Literature, Music, and French (the language-department representative).
   Record each page's exact URL.

### Cache format (locked here, reused verbatim by increment 3)

- File: `data/raw/<sha256(url).hexdigest()>.html`, raw response bytes decoded with declared charset or UTF-8-with-replacement.
- Ledger: append one JSON line per successful fetch to `data/raw/manifest.jsonl`: `{"url": ..., "sha256": ..., "date_fetched": "YYYY-MM-DD", "status": 200}`.
  `date_fetched` matters: increment 6 derives corpus doc ids from it, so it is the durable record of when the HTML snapshot was taken.
- The spike uses a throwaway `backend/scripts/spike_fetch.py` implementing exactly this; increment 3's fetcher must read cache files the spike wrote.

### Verification checklist (run against the cached HTML, record pass/fail plus counts per dept)

- `.courseblock` present and plausible in count (CS should exceed 50).
- `.courseblocktitle` text parses as `<code> <title>. <points> points`; record 5 verbatim examples per dept.
- `.courseblockdesc` present; contains the prereq prose when one exists.
- Prereq hyperlinks: anchors matching `a[href*="/search/?P="]` inside courseblock content; record the exact href format and the URL-encoded code format.
- Term subheadings: lines matching `^(Fall|Spring|Summer) \d{4}: ` with course code and instructor names; record 3 verbatim examples and where they sit in the DOM relative to the courseblock.
- `.sc_courselist` requirement tables: present on the dept page or a linked majors page; record which, plus the column classes seen (`codecol`, hourscol, etc.).
- Course-code shapes: collect every distinct code pattern seen (`COMS W1004`, `ECON UN1105`, `HUMA UN1123`, cross-school forms) and finalize the normalization regex.
  The regex proposed to doc 02 is `^[A-Z]{2,4} [A-Z]{1,2}[0-9]{4}$` after uppercasing and whitespace-collapse; widen it here if real HTML demands and record the final form as THE decision.

## Findings doc template

`docs/notes/day1_spikes.md` sections, in order: `CULPA findings`, `CULPA decision` (one matrix row plus rationale), `Bulletin fetch log` (URLs, hashes, dates), `Selector checklist results` (table per dept), `Course-code regex: final`, `Anomalies and parser implications`.
Date-stamp the doc.

## Exit criteria

- All 6 bulletin pages cached under `data/raw/` with manifest lines.
- Selector checklist completed for all 5 departments; course-code regex finalized.
- CULPA decision recorded as exactly one matrix outcome.
- `docs/notes/day1_spikes.md` committed.
- No production module written in this increment; `spike_fetch.py` stays, marked as superseded by `catalog/fetch.py` in increment 3.
