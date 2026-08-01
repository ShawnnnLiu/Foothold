# Increment 7: CULPA Ingest (NETWORK, shape-dependent)

Goal: professor ratings and review signal joined onto the catalog, fully optional and degradable, closing the Week 1 milestone: `make build-data` green end-to-end.
The concrete client implementation is selected by the increment 1 spike decision recorded in `docs/notes/day1_spikes.md`; this doc fixes everything that does not depend on it.
Network gate: user go-ahead before any CULPA request.

## Invariants regardless of spike outcome

- Every CULPA-derived field in every artifact and contract is optional; the build is green with zero CULPA data.
- `--skip-culpa` (and the spike outcome `skip`) short-circuits stage 4 into a no-op that still writes empty tables, so downstream SQL never special-cases absence.
- Raw responses are cached under `data/raw/culpa/` (gitignored) with a manifest, same discipline as the bulletin cache; derived tables are deterministic functions of the cache, so `--check` stays offline-stable.
- Per-unit fault isolation: a failing professor or department slice is logged into the report and skipped, never fatal.
- Politeness: 1 req/s, 20 s timeout, no retries, fixed UA, robots respected if the source is a website rather than an API.

## Contracts (spec: `docs/specs/culpa.schema.md`)

`contracts/culpa.py`:

- `CulpaProfessor`: `professor_id: str`, `name` (1..120), `avg_rating: float | None` (0..5), `nugget: Literal["gold", "silver", None]` (verify the real nugget taxonomy against the spike; adjust spec first if different), `review_count: int >= 0`.
- `CulpaReview`: `review_id`, `professor_id`, `course_code: str | None` (normalized when present), `text` (1..5000, control-char hygiene), `agree_count: int >= 0`, `date: date | None`.
- `CourseRating` (the derived, catalog-facing record): `course_code`, `avg_rating: float | None`, `review_count: int`, `top_review_excerpt: str | None` (<= 280), `best_prof_name: str | None`, `best_prof_nugget: str | None`.

All registered in the schema registry with fixtures.

## `catalog/culpa.py`

- `CulpaClient` Protocol: `fetch_departments()`, `fetch_professors(dept)`, `fetch_reviews(professor_id)`; the live implementation matches the spike-recorded endpoints; a `CachedCulpaClient` replays `data/raw/culpa/`; tests use fixture payloads.
- Join policy, locked (plan pipeline step 4):
  1. Primary: reviews carrying a `course_code` join directly after `normalize_course_code`.
  2. Secondary: professors join to courses via name intersection with offering instructors.
     Name normalization for the intersection, locked: casefold, collapse whitespace, strip periods, drop single-letter middle tokens; compare full normalized strings for equality.
     Ambiguity policy: a professor name matching instructors on more than 8 distinct courses is skipped as too-common (logged, not fatal).
- `course_ratings` derivation, locked and deterministic:
  - `avg_rating`: mean of joined professors' `avg_rating` weighted by their `review_count`, 2-decimal rounding; null when no joined professor has a rating.
  - `review_count`: count of joined reviews.
  - `top_review_excerpt`: from the joined review with the highest `agree_count`, tie by most recent date, then by `review_id` ascending; clipped to 280 chars at a word boundary with an ellipsis.
  - `best_prof_name`/`best_prof_nugget`: the joined professor with the highest `avg_rating` among those with `review_count >= 3`, tie by name ascending.

## Store and build stage 4

DDL appended to the catalog component (bump `ensure_schema` version to 2; version bump is safe because the artifact is regenerated, not migrated):

```sql
CREATE TABLE IF NOT EXISTS culpa_professors (
    professor_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS culpa_reviews (
    review_id TEXT PRIMARY KEY, professor_id TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS course_ratings (
    course_code TEXT PRIMARY KEY, payload TEXT NOT NULL);
```

`build_catalog.py --stage culpa`: fetch-or-replay into cache, parse into contracts, run the join, write the three tables sorted by primary key, `VACUUM`; report `data/reports/culpa_report.json` (committed, deterministic): joined-by-code count, joined-by-name count, skipped-too-common list, per-unit failures with reason codes.
If the spike decision is `skip` or `static-fallback`, implement only that branch; do not build speculative clients for outcomes that did not happen.

## Tests

- Join: fixtures covering code-join, name-join with normalization edge cases (middle initials, periods, case), too-common skip, no-match leaves course absent from `course_ratings`.
- Derivation: hand-computed rating/excerpt/best-prof cases including all tie-breaks and the null paths.
- `--skip-culpa`: full build green, empty tables present, report says skipped.
- Cache replay determinism: two stage-4 runs from the same cache produce identical canonical dumps.

## Exit criteria (Week 1 milestone, Aug 6)

- `make build-data` green end-to-end: fetch, parse, prereqs (cache-served), culpa (or skip), corpus.
- `catalog.db` + `corpus.db` committed; all reports committed and reviewed; parse report clean for demo majors.
- `--check` green offline for both artifacts; `make check` green.
- The AI tool disclosure ledger in the roadmap re-confirmed: Claude Code, Claude API (`claude-sonnet-5` extractor), plus anything new this week.
