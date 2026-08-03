# Evaluator Hand-Verification: the S10b Demo Evaluation

Hand verification of the S10b milestone CLI run against RENDERED assist.org agreement pages, performed 2026-08-02 with the user's network go-ahead.
The standing rule from `docs/notes/articulation_spotchecks.md` applies: every check below compares evaluator output against what ASSIST renders to a human, never against the API payload the build already read, because reading our own input back proves nothing.
Spotchecks section 12 established that `templateOverrides` is renderer-ignored, so the stored `sending_expr` IS the rendered rule and no override avoidance was needed.

Request accounting: 4 rendered page loads (each fetching its ~6 SPA endpoints), well inside the ~50-55 requests-per-session ASSIST meter.

## The demo student and how it was composed

`data/curated/demo_students/deanza_ucsd_cs.json`: nine De Anza courses, evaluated against the Mathematics/Computer Science B.S. major (key `76/113/to/7/Major/d2dfb7a8-d505-4e70-f33c-08ddd3b241a4`) with all 50 receiving-side department agreements of the pair in the bundle.

Doc 03's locked composition criteria, and how each was met:

- 8-10 courses: nine (MATH 1A, 1B, 1C, 2A, 2B, 22; CIS 22B, 22C, 36B).
- The honors-or-regular clean matches: MATH 1A, MATH 1B, MATH 2A, CIS 22C, CIS 36B all present, joined by MATH 2B and MATH 22 as realistic CS-transfer additions.
- Exactly one half-series: MATH 1C without MATH 1D, producing `partial_series` on MATH 20C and MATH 20E, in the major and the MATH department agreement each.
- The `no_articulation` pick, from querying the built artifact (never guessed): of De Anza's 301-course vocabulary, 133 courses articulate at another corridor target but appear in NO De Anza -> UCSD sending expression.
  CIS 22B (Intermediate Programming Methodologies in C++, 4.5 units) was chosen because it is CIS 22C's own prerequisite, so a real CS transfer student would hold it, and it articulates at eight other corridor targets (SJSU CS 46A and CS 49C, UCLA COM SCI 31, UC Davis ECS 036A/B, Cal Poly SLO CSC 202, CSUN COMP 182/182L, CSULB CECS 274, UCR CS 10B, UCI) while UCSD publishes nothing for it.
- Every bucket represented: 14 `transfers_clean`, 4 `partial_series` (at risk), 1 `no_articulation`, 2 `still_owed`; 21 findings total.

Units by the demo run: clean 34.0, at risk 5.0, no articulation 4.5, still owed 10.0; dollars at the UCSD rate: at risk $1,455.00, no articulation $1,309.50.

The CLI invocation (defaults resolve to the committed artifact, demo student, and curated cost table):

```bash
cd backend && uv run python scripts/evaluate_student.py \
  --major-key "76/113/to/7/Major/d2dfb7a8-d505-4e70-f33c-08ddd3b241a4"
```

## Check 1: the major agreement page

Source: <https://assist.org/transfer/results?year=76&institution=113&agreement=7&agreementType=to&view=agreement&viewBy=major&viewByKey=76/113/to/7/Major/d2dfb7a8-d505-4e70-f33c-08ddd3b241a4> ("Mathematics/Computer Science B.S.", effective 2025-2026).

Every finding citing the major key, against the rendered rule:

| Finding | Cited position | assist.org renders | Result |
|---|---|---|---|
| `transfers_clean` MATH 2A -> MATH 20D | 0 | MATH 2A **OR** MATH 2AH | match |
| `transfers_clean` MATH 1B -> MATH 20B | 1 | MATH 1B **OR** MATH 1BH | match |
| `transfers_clean` MATH 2B -> MATH 18 | 2 | MATH 2B **OR** MATH 2BH | match |
| `partial_series` MATH 1C -> MATH 20E | 3 | MATH 1C **AND** MATH 1D (no honors branch) | match; missing MATH 1D correct |
| `partial_series` MATH 1C -> MATH 20C | 4 | (MATH 1C **AND** MATH 1D) **OR** (MATH 1CH **AND** MATH 1DH) | match; missing MATH 1D correct |
| `transfers_clean` MATH 1A -> MATH 20A | 5 | MATH 1A **OR** MATH 1AH | match |
| `transfers_clean` CIS 36B -> CSE 11 | 6 | CIS 35A **OR** CIS 36B | match |
| `transfers_clean` CIS 22C -> CSE 12 | 7 | CIS 22C **OR** CIS 22CH | match |

None of these rendered rows carries an advisement, matching the findings' empty `advisements` lists.
The page's "NOTE: If no 20E equivalency is listed below..." paragraph is agreement-level general information, not a row advisement, and correctly reaches no finding.

Still-owed, against the rendered template:

| Finding | assist.org renders | Result |
|---|---|---|
| `still_owed` detail `MATH 20C and MATH 20E`, 8.0 units, citing position 4 | Group 1 requires all of MATH 18, 20A, 20B, 20C, 20D, 20E; the student run satisfies all but 20C and 20E; each renders at 4.00 units, so 4 + 4 = 8 | match; citation is the first owed cell's articulation (MATH 20C, position 4) |
| `still_owed` detail `CSE 15L or CSE 29`, 2.0 units, citing position 0 | Group 4 "Select A or B": CSE 15L (2.00 units, No Course Articulated) or CSE 29 (4.00 units, No Course Articulated) | match; Or-group owed units are the cheapest section, min(2, 4) = 2; neither cell has an articulation so the citation falls to position 0 per doc 03 |

The smoke baseline run without MATH 2B owes `MATH 18 and MATH 20C and MATH 20E` at 12.0 units (3 x 4.00), which the same rendered group confirms.

## Check 2: the Computer Science and Engineering department page

Source: <https://assist.org/transfer/results?year=76&institution=113&agreement=7&agreementType=to&view=agreement&viewBy=dept&viewByKey=76/113/to/7/Department/3276>.

| Finding | Cited position | assist.org renders | Result |
|---|---|---|---|
| `transfers_clean` CIS 36B -> CSE 11 | 0 | CIS 35A **OR** CIS 36B | match |
| `transfers_clean` CIS 22C -> CSE 12 | 1 | CIS 22C **OR** CIS 22CH | match |
| `transfers_clean` MATH 22 -> CSE 20 | 3 | MATH 22 **OR** MATH 22H | match |

The rendered "Same as MATH 15A" tag on CSE 20 is a cross-listing annotation, not a transfer rule, per spotchecks section 9.
CIS 22B appears nowhere on the rendered page, supporting its `no_articulation` finding.

## Check 3: the Mathematics department page

Source: <https://assist.org/transfer/results?year=76&institution=113&agreement=7&agreementType=to&view=agreement&viewBy=dept&viewByKey=76/113/to/7/Department/8952>.

| Finding | Cited position | assist.org renders | Result |
|---|---|---|---|
| `transfers_clean` MATH 22 -> MATH 15A | 4 | MATH 22 **OR** MATH 22H | match |
| `transfers_clean` MATH 2B -> MATH 18 | 5 | MATH 2B **OR** MATH 2BH | match |
| `transfers_clean` MATH 1A -> MATH 20A | 6 | MATH 1A **OR** MATH 1AH | match |
| `transfers_clean` MATH 1B -> MATH 20B | 7 | MATH 1B **OR** MATH 1BH | match |
| `partial_series` MATH 1C -> MATH 20C | 8 | (MATH 1C **AND** MATH 1D) **OR** honors pair | match |
| `transfers_clean` MATH 2A -> MATH 20D | 9 | MATH 2A **OR** MATH 2AH | match |
| `partial_series` MATH 1C -> MATH 20E | 10 | MATH 1C **AND** MATH 1D | match |

CIS 22B appears nowhere on this page either.
The dept page also renders MATH 10B and MATH 10C as "No Course Articulated", the stored `sending_expr = None` shape, and the evaluator correctly emits nothing for them.

## Check 4: CIS 22B articulates elsewhere (the projection pick is real)

Source: <https://assist.org/transfer/results?year=76&institution=113&agreement=39&agreementType=to&view=agreement&viewBy=major&viewByKey=76/113/to/39/Major/3ccc93fd-a5dc-4e22-3433-08ddb349963e> ("Computer Science, B.S.", De Anza -> San Jose State, 2025-2026).

The rendered CS 46A rule is CIS 35A **OR** (CIS 22A **AND** CIS 22B) **OR** (CIS 22A **AND** CIS 22BH) **OR** (CIS 36A **AND** CIS 36B) **OR** CIS 27, and CS 49C accepts (CIS 22A **AND** CIS 22B) as one branch, each sequence branch carrying the "Complete entire sequence at same institution prior to transfer" advisement.
That matches the artifact query (CIS 22B in SJSU positions 2 and 19) and proves the demo's `no_articulation` course is a real course with real articulation value elsewhere, exactly the story the finding tells.

## Dollar totals, verified by hand against the curated cost table

`data/curated/costs.json` carries the user-confirmed 2026-08-02 figures; UCSD (institution 7) is $291.00 per unit (Summer Session 2026, the published per-unit price of retaking a unit there).

| Quantity | Hand computation | CLI output | Result |
|---|---|---|---|
| at_risk_dollars | 5.0 units x 291.00 = 1,455.00 | $1,455.00 | match |
| no_articulation_dollars | 4.5 units x 291.00 = 1,309.50 | $1,309.50 | match |

Cal Poly SLO (11), San Diego State (26), and CSU Fullerton (129) publish no per-unit rate (flat tiers or bundles only), so they have no row and their evaluations honestly render dollars as "unknown (no cost row)", never zero.

## Mechanical baselines re-proven this split

- The kickoff smoke baseline reproduces exactly at the CLI: MATH 1A/1B/2A (5.0 each) + MATH 1C (5.0) + CIS 22C/36B (4.5 each) against the same major yields 16 findings (10 `transfers_clean`, 4 `partial_series` on MATH 20C/20E in major and MATH dept each, 2 `still_owed`), units clean 24.0, at risk 5.0, still owed 14.0, dollars None without a cost table.
- All 168 latest-year majors of De Anza -> UCSD evaluate and project to triage boards crash-free with the smoke request set.
- `make check` green (see the split's commit); the scenario exhaustiveness test still proves one named fixture per `EvaluationFindingCode`.

## Honest limits of this verification

- Hand-checks cover the three demo-pair agreements the student's findings cite plus one SJSU agreement; the other 165 majors of the pair are proven crash-free, not hand-read.
- CIS 22B's absence from ALL 218 De Anza -> UCSD agreements is an artifact-level query result; the rendered confirmation covers the three agreements above.
- A satisfied requirement group's advisements are absent from the findings object by the amended doc 03 decision (re-deferred to the Week 2 board rendering, recorded in the amendment); nothing on the checked pages contradicted a finding, but grade-minimum texts on satisfied groups are not yet surfaced anywhere.
- The checked rows carry no advisements on the rendered pages, so this split exercises the empty-advisement path against ground truth; the advisement-bearing path is fixture-proven (`advisement_note.json`) but not yet hand-checked against a rendered page.
