# Day-1 Risk Spike Findings

Date: 2026-07-31.
Produced by increment 1 (`docs/week-1-implementations/01-day1-risk-spikes.md`).
Consumed by docs 03 (bulletin fetch/parse) and 07 (CULPA ingest).

## CULPA findings

DNS (2026-07-31):

- `dig +short api.culpa.info` returned nothing (no record; the host observed dead on 2026-07-30 is permanently gone, not flaky).
- `dig +short culpa.info` returned `104.21.81.182` and `172.67.145.172` (Cloudflare).
- `dig +short www.culpa.info` returned the same two Cloudflare IPs.

Site probe:

- `GET https://culpa.info/` returned 200.
  The body is a React SPA shell (`modern-culpa.svg` favicon, single bundle `/static/js/main.fdf53ba7.js`, flytedesk ad script, Cloudflare insights beacon).

API host discovery (spike step 4, via the SPA bundle rather than live browser network capture; the bundle is the ground truth for what the frontend calls):

- The frontend calls a same-origin API under `https://culpa.info/api/`.
  There is no separate API host.
- Endpoint paths extracted verbatim from the bundle:
  - `api/departments/all`, `api/departments/${n}/courses`, `api/departments/${n}/professors`
  - `api/course_page/card/${e}`, `api/professor_page/card/${e}`
  - `api/review/course/${e}`, `api/review/professor/${e}`
  - `api/course/search`, `api/professor/search`, `api/search/search`
  - `api/front_page`
  - write/admin paths not relevant to us: `api/vote`, `api/flag`, `api/review/new`, `api/authentication/*`, `api/*/pending`, `api/*/approve`, `api/syllabus/*`
- Corroboration: `HoldenB2007/ProfRater` (Chrome extension, pushed 2026-07-13) calls the same host and paths, e.g. `https://culpa.info/api/professor/search?queryString=...&maxResults=20` and `api/professor_page/card/${professorId}`, and documents nugget values `0=None, 1=Bronze, 2=Silver, 3=Gold`.

Endpoint probes (GET, browser UA, 20 s timeout; status plus first bytes recorded, no bulk download):

- `GET /api/front_page` -> 200, JSON: `{"most_recent_reviews": [{"agree_count": 0, "content": "This is an amazing class..."}, ...]}`.
- `GET /api/departments/all` -> 200, JSON list: `{"department_code": "COMS", "department_id": 7, "name": "Computer Science"}` (also HIST=1, AFAM=3, ANTH=4, EALC=8, ECON=9, ENCL=10, ...).
- `GET /api/departments/7/courses` -> 200, 152 courses, each `{"course_code": "COMS W3134", "course_id": 4, "department_id": 7, "name": "Data Structures in Java", "status": "approved"}`.
  Course codes use the bulletin's own format (`COMS W3134`, `CSEE W3826`), so the join to catalog courses is direct.
- `GET /api/departments/6/courses` -> 200, `[]` (some departments are empty; ingest must tolerate this).
- `GET /api/departments/7/professors` -> 200, each `{"first_name": "Jonathan", "last_name": "Gross", "nugget": 1, "professor_id": 40, "status": "approved", "uni": null}`.
- `GET /api/course_page/card/4` -> 200: `{"course_summary": {"avg_rating": null, "course_header": {...}, "num_reviews": 94}, "professors_that_taught": [{first_name, last_name, nugget, professor_id, uni}, ...]}`.
  Note `avg_rating` was null for this course card; per-professor ratings likely live on `professor_page/card`.
- `GET /api/review/course/4` -> 200: `{"number_of_reviews": 87, "reviews": [{"agree_count": 2, "content": "The course itself isn't too challenging..."}, ...]}`.
  Reviews ARE course-associated: this endpoint returns reviews per course id directly.

GitHub:

- `github.com/culpaonline` does not exist (404 on both the org and user API endpoints); the plan's pointer is stale.
- The only official-looking code is the legacy `culpa-team/api` repo ("The RESTful API to access CULPA data", last push 2015, no detected language).
  It predates the current site and documents nothing about `culpa.info/api`.
- No static data export exists anywhere findable.

## CULPA decision

Outcome: `adapted`.

Rationale: the API is alive and serves everything doc 07 needs (departments with codes, per-department course lists keyed by bulletin-format course codes, per-course review lists, professor nuggets), but on a different host than planned (`https://culpa.info/api/*`, same-origin with the site, instead of the dead `api.culpa.info`) and with shapes discovered from the SPA bundle rather than the nonexistent `culpaonline` repos.
Doc 07's client section must be rewritten against the endpoints and payload shapes recorded above before execution.

Ingest implications for doc 07:

- Enumerate `api/departments/all`, then `api/departments/{id}/courses` per department; join to catalog by exact `course_code` (formats already match).
- `api/review/course/{course_id}` gives course-associated reviews with `agree_count` for excerpt ranking; `number_of_reviews` and card `num_reviews` may differ slightly (94 vs 87 observed), so count from the reviews payload.
- Professor nugget scale: 0=None, 1=Bronze, 2=Silver, 3=Gold; `uni` is often null.
- Course-card `avg_rating` can be null; treat every rating field as optional.
- Filter on `status == "approved"` defensively; pending items exist in the schema.
- Politeness: same-origin Cloudflare-fronted site; keep 1 req/s, fixed browser UA, and per-department fault isolation.

## Bulletin fetch log

Index URL verified correct: `https://bulletin.columbia.edu/columbia-college/departments-instruction/` returned 200 (no correction needed).

All fetches on 2026-07-31, status 200, via `backend/scripts/spike_fetch.py` (1 req/s, 20 s timeout, fixed browser UA), cached as `data/raw/<sha256(url)>.html` with one `manifest.jsonl` line each:

| URL | sha256 | bytes |
|---|---|---|
| `.../departments-instruction/` | `67875fa38788dc1afc9b566de309466057c0724933ce03e70c6510674c4ff8d6` | 32176 |
| `.../departments-instruction/computer-science/` | `d046352ac117dc353797070d1f16999742a79a0da8822e90a3e94d5704f459d5` | 296767 |
| `.../departments-instruction/economics/` | `f867b5fe9430e2a094866347b73cb51d2c1f57d885189af0f3092f580c59c11b` | 320023 |
| `.../departments-instruction/english-comparative-literature/` | `19785ed442a7b04c18f5d2a5394e543da8e131bad46c3203cc98a0784786e6bf` | 265834 |
| `.../departments-instruction/french-romance-philology/` | `3d18b8ec00ca27b627b775b8b04a791825266d5db7fd66696e65814a308c720f` | 136248 |
| `.../departments-instruction/music/` | `fb2e059e03d340adfe60f09545ae90eee6d769be7ddc31bd6076f97e83dd8806` | 465617 |

Note the French department URL slug is `french-romance-philology` (the index anchor text is "French").

## Selector checklist results

Counts per department (from cached HTML, stdlib HTML parser):

| Check | CS | Econ | English | French | Music |
|---|---|---|---|---|---|
| `.courseblock` count | 129 | 53 | 63 | 28 | 131 |
| `.courseblocktitle` count | 131 | 53 | 63 | 28 | 133 |
| titles parsing as `<code> <title>. <points> points` | 131/131 | 53/53 | 63/63 | 28/28 | 131/133 |
| `.courseblockdesc` count | 130 | 53 | 63 | 28 | 131 |
| descs containing prereq/coreq prose | 83 | 47 | 9 | 16 | 2 |
| prereq anchors `a[href*="/search/?P="]` in blocks | 225 | 212 | 10 | 27 | 0 |
| term subheading matches | 184 | 147 | present | 57 | 571 |
| `.sc_courselist` tables on dept page | 16 | 12 | 0 | 5 | 10 |

Pass/fail: every check passes except `.sc_courselist` on English (see anomalies) and the 2 Music title outliers (see anomalies).
CS `.courseblock` count 129 exceeds the required 50.

`.courseblocktitle` verbatim examples (5 per dept):

- CS: `COMS W3998 UNDERGRAD PROJECTS IN COMPUTER SCIENCE. 1.00-3.00 points.`; `COMS W4901 Projects in Computer Science. 1-3 points.`; `COMS E0001 FOUND OF COMPUT SCI-TRACK. 0.00 points.`; `COMS W1002 COMPUTING IN CONTEXT. 4.00 points.`; `COMS W1004 Introduction to Computer Science and Programming in Java. 3.00 points.`
- Econ: `ECON UN1105 PRINCIPLES OF ECONOMICS. 4.00 points.`; `ECON UN3211 INTERMEDIATE MICROECONOMICS. 4.00 points.`; `ECON UN3213 INTERMEDIATE MACROECONOMICS. 4.00 points.`; `ECON UN3412 INTRODUCTION TO ECONOMETRICS. 4.00 points.`; `ECON UN2105 THE AMERICAN ECONOMY. 3.00 points.`
- English: `ENGL UN2000 Approaches to Literary Study. 4.00 points.`; `ENGL UN2001 Approaches to Literary Study Seminar. 0.00 points.`; `ENGL UN1335 Shakespeare I. 3.00 points.`; `ENGL UN2100 Drama Before Shakespeare. 3.00 points.`; `ENGL UN3329 What Shakespeare Read. 4.00 points.`
- French: `FREN UN1101 ELEMENTARY FRENCH I. 4.00 points.`; `FREN UN1102 ELEMENTARY FRENCH II. 4.00 points.`; `FREN UN1105 ACCELERATED ELEM FRENCH. 8.00 points.`; `FREN UN2101 INTERMEDIATE FRENCH I. 4.00 points.`; `FREN UN2102 INTERMEDIATE FRENCH II. 4.00 points.`
- Music: `AHMM UN3320 MUSIC IN EAST ASIA. 3.00 points.`; `AHMM UN3321 MUSICS OF INDIA ＆ WEST ASIA. 3.00 points.`; `HUMA UN1123 Music Humanities. 3.00 points.`; `MUSI UN1002 FUNDAMENTALS OF MUSIC. 3.00 points.`; `MUSI UN1350 Introduction to Musicianship. 1.00 point.`

Prereq hyperlinks: exact href format is `/search/?P=<DEPT>%20<CODE>` (space URL-encoded as `%20`), anchor text is the plain code.
Examples: `/search/?P=ENGI%20E1006` ("ENGI E1006"), `/search/?P=COMS%20W1004` ("COMS W1004"), `/search/?P=MATH%20UN1101` ("MATH UN1101"), `/search/?P=FREN%20W2202` ("FREN W2202").

Term subheadings: 3 verbatim examples (header text): `Fall 2026: COMS W1002`; `Spring 2026: ECON UN1105`; `Spring 2026: FREN UN1101`.
DOM position: inside each `.courseblock`, a `div.desc_sched` contains `div.desc_sched_header` holding `<strong>(Fall|Spring|Summer) YYYY: CODE</strong>`, followed by `table.scheduletbl` whose rows carry section number, times/location, instructor name, points, and enrollment.
Instructor names are NOT on the subheading line; they are in the Instructor column of the adjacent `scheduletbl` (e.g. `Fall 2026: COMS W1002` -> table row `COMS 1002 | 001/13508 | T Th 1:10pm-2:25pm ... | <instructor> | ...`).

`.sc_courselist` requirement tables: present on the department page itself for CS (16), Econ (12), French (5), Music (10).
Column classes seen: `codecol`, `hourscol`, `orclass` (the `orclass` row class marks "or" alternatives).
English has ZERO `.sc_courselist` tables; its Requirements tab (`#requirementstextcontainer`) is prose-only (advising text plus category descriptions), not a structured table.

## Course-code regex: final

Distinct code shapes observed across all five departments (letters as A, digits as 9):

- `AAA AA9999` (39 codes, e.g. `MPP UN1401`)
- `AAAA A9999` (130 codes, e.g. `CBMF W4761`, `COMS E0001`)
- `AAAA AA9999` (175 codes, e.g. `AHMM UN3320`, `CLEN GU4122`)

No trailing letters, lowercase forms, or other shapes appeared.
The proposed regex needs no widening.

Final decision: after uppercasing and whitespace-collapse, the normalization regex is `^[A-Z]{2,4} [A-Z]{1,2}[0-9]{4}$`.

## Anomalies and parser implications

1. Mislabeled title paragraphs (Music): one courseblock (`MUSI UN3321 MUSIC THEORY III.`) contains a SECOND `p.courseblocktitle` whose text is description prose ("Intermediate analysis and composition in a variety of tonal idioms."), while its real `p.courseblockdesc` is empty and other prose sits in a class-less `<p>`.
   Implication: parse per `.courseblock` and take the first `.courseblocktitle` (or the first whose text matches the title regex); never assume title count equals block count; harvest description text from all non-title `<p>` children when `courseblockdesc` is empty.
2. Title/block count mismatch (CS 131/129, Music 133/131) plus outright duplicate courseblocks (CS lists `COMS W3998` and `COMS W4901` twice on the page).
   Implication: dedupe parsed courses by normalized code; identical duplicates are expected.
3. Title markup varies: usually one `<strong>` holding the whole line, but sometimes split (`<strong>MUSI UN3321 MUSIC THEORY III.</strong> <strong><em>3 points</em>.</strong>`).
   Implication: parse the normalized text content of the whole title element, not its markup structure.
4. Points formats: `4.00 points`, `3 points`, `1.00 point` (singular), `0.00 points`, and ranges `1.00-3.00 points` and `1-3 points`.
   Working title regex from the checklist: `^(?P<code>[A-Z]{2,4} [A-Z]{0,2}\d{4}[A-Z]?) (?P<title>.+?)\. (?P<pts>[\d.]+(-[\d.]+)?) points?\.?$` against whitespace-normalized text (it parsed 406 of 408 titles; the 2 misses are anomaly 1).
5. Unicode in titles: fullwidth ampersand U+FF06 (`MUSICS OF INDIA ＆ WEST ASIA`) and non-breaking spaces appear.
   Implication: NFKC-normalize (or at least map U+FF06 and U+00A0) before parsing and storage.
6. Legacy code forms inside prereq anchors: French anchors reference `FREN W2202` and `FREN W3333` (old `W` prefix) although the canonical bulletin codes are now `UN`/`GU` prefixed.
   Implication: a prereq link can point at a code that no longer appears as any courseblock's own code; prereq resolution must tolerate unresolvable codes rather than assume closure.
7. English is prereq-sparse and table-free: only 9 descs mention prereqs, 10 prereq anchors, and requirements are prose (seminars gate on instructor permission).
   Implication: instructor-permission style gates become `note` leaves (never silently satisfied, per the axioms); requirement-group extraction cannot rely on `.sc_courselist` existing for every department.
8. Music has near-zero prereq prose (2 descs) but heavy term data (571 term-subheading matches, some courses offered in many terms).
   Implication: term-offering extraction must handle many `desc_sched` blocks per course.
9. Empty `.courseblockdesc` elements exist (CS has 130 descs for 129 blocks, Music has one empty).
   Implication: treat description as optional prose, not a required field.
