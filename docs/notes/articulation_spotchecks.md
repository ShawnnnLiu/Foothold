# Articulation Artifact Spot Checks

Hand verification of `data/articulation.db` against assist.org, performed during split S9c on 2026-08-02.
Every check below compares what the artifact stores against what ASSIST RENDERS to a human, not against the API payload the build already read.
That distinction is the point: reading our own input back proves nothing about whether the expression mapping means what the agreement says.

Source of truth for the demo pair: <https://assist.org/transfer/results?year=76&institution=113&agreement=7&agreementType=to&view=agreement&viewBy=major&viewByKey=76/113/to/7/Major/76ab1c59-2dcf-4c6f-f364-08ddd3b241a4> ("CSE: Computer Science B.S.", De Anza College to UC San Diego, 2025-2026).

Attribution, per the ASSIST terms-of-use assessment in `docs/notes/assist_spike.md`: "Data: ASSIST.org, the official California articulation repository".

## 1. Corridor scope for the demo pair

| Fact | assist.org | Artifact | Result |
|---|---|---|---|
| Academic year resolved | 2025-2026 (year id 76) | 76 | match |
| Major reports | 168 | `major_reports` 168, `major_selected` 168 | match |
| Department reports | 86 | `dept_reports` 86, `dept_selected` 50 | match, and see note below |

The 36 unselected department reports are the `SendingDepartment` mirror direction, which `docs/specs/agreement.schema.md` puts out of scope for v1.
Verified before filtering them: those 36 agreements publish 120 articulation pairs, all 120 of which the 50 receiving-side agreements also publish, and those publish 329 further pairs the mirrors do not.
Dropping them therefore removes duplicates, not transfer rules.

## 2. Expression operators, the check that matters most

A wrong operator here would silently tell a student they have credit they do not have.
Every row was read off the rendered agreement and compared to the stored `sending_expr`.

| Receiving course | assist.org renders | Artifact stores | Result |
|---|---|---|---|
| CSE 11 | CIS 35A **OR** CIS 36B | `{"any": [CIS 35A, CIS 36B]}` | match |
| CSE 12 | CIS 22C **OR** CIS 22CH | `{"any": [CIS 22C, CIS 22CH]}` | match |
| CSE 20 | MATH 22 **OR** MATH 22H | `{"any": [MATH 22, MATH 22H]}` | match |
| CSE 30 | (CIS 21JA **AND** CIS 21JB **AND** CIS 26B) **OR** (CIS 21JA **AND** CIS 21JB **AND** CIS 26BH) | `{"any": [{"all": [...26B]}, {"all": [...26BH]}]}` | match |
| MATH 20C | (MATH 1C **AND** MATH 1D) **OR** (MATH 1CH **AND** MATH 1DH) | `{"any": [{"all": [1C, 1D]}, {"all": [1CH, 1DH]}]}` | match |

The honors-or-regular pattern and the nested series-or-series pattern both round-trip, which is the shape the evaluator's `partial_series` logic depends on.

## 3. "No Course Articulated"

The rendered agreement shows CSE 21, CSE 29, PHYS 4A, and PHYS 4B as "No Course Articulated".
In the artifact these are template cells with no matching articulation entry, so they store as unmet requirement cells rather than as articulations with an empty rule - the distinction the overview doc's payload facts require, and what lets the UI render them as owed rather than as satisfied.

Checked separately in the department agreement: MATH 10B and MATH 10C carry `sending_expr = None`, the `sendingArticulation: null` encoding of the same fact.

## 4. Advisements

The artifact carries advisement text that the pre-S9c build was dropping without record, for example "Articulation is subject to placement by proficiency exam" (8 instances in the demo pair) and "Must be taken for a letter  grade" (double space preserved verbatim from ASSIST).
Group and course level texts become `note` leaves INSIDE their group node, so no advisement can be satisfied by taking the course alone.

## 5. Corridor totals

Built 2026-08-02 from a 3,889-request fetch (98 minutes, 3,888 successes and one auto-recovered 429).

| | |
|---|---|
| Pairs walked | 464 (460 resolved to year 76; 4 publish no agreements at all) |
| Agreements stored | 2,972, none excluded |
| Articulations stored | 27,452 |
| Requirement groups stored | 2,278 |
| CC course vocabulary | 6,957 |
| Target course vocabulary | 568 |
| `articulation.db` | 17 MB |

`make build-check` regenerates both artifacts from the same cache with identical canonical dumps.

### The course-code widening

The first full build excluded 1,624 articulations (~6%) as `course_code_unparseable` across 150 distinct codes, none of which were malformed: `COURSE_CODE_RE` had been written from the De Anza-to-UCSD captures alone.
After widening the regex and fixing the normalizer's handling of ASSIST's uneven part formatting, that count is **7**, and all 7 are payloads where `prefix` and `courseNumber` are genuinely null.

Confirmed present in the artifact afterwards, none of which existed in it before:

| Shape | In artifact |
|---|---|
| Digit in prefix | 661 articulations on `BUS1 20`, `BUS2 90`, `BUS3 10`, `BUS3 80`, `BUS4 91L`, `IN4MATX 43` |
| Campus-suffix token | 102 CC courses, e.g. `ACCT 101 C`, `AJ 100 F`, `ANAT 231 F` |
| Leading hyphen | 49 CC courses, e.g. `ACTG -04A`, `BIOL -01` |
| Decimal number | 16 CC courses, e.g. `BIO 2.1`, `BIO 2.3` |

The San Jose State business courses matter disproportionately, since "business" is one of the five pinned major keywords: the corridor was silently missing a chunk of exactly the majors it was built to cover.

## 6. Known gaps, measured rather than assumed

These are deliberate v1 cuts. The numbers are the demo pair's, and they are recorded here so the increment that closes them knows what it buys back.

| Gap | Corridor cost | Why deferred |
|---|---|---|
| `NFromConjunction` / `NFromArea` / `Following` template instructions | 6,984 requirement groups excluded | "Select N from these" is unmodeled; storing the group without its rule would read as "complete all of" |
| ASSIST `Series` articulation type | 1,614 articulations excluded | Doc 02 locks unknown types to typed exclusion; modelling series is an articulation-contract change |
| `NFollowing` section selection rules | 635 exclusions | Same family, reached through the advisement gate |
| `mixed_group_conjunction` | 12 exclusions | Genuinely inexpressible as one node; not a deferral |
| Null course parts | 7 exclusions | The payload carries no prefix or number; correctly excluded |

All of them surface as typed `reason_code` entries in `data/reports/assist_build_report.json`; none is a silent drop.

The N-from family dominates, and it matters most for the "requirements still owed" half of the product: 6,984 excluded groups against 2,278 stored ones means the triage board is substantially thinner than the real agreement for most majors.
That is the single largest known gap in the artifact and the strongest candidate for the next increment.
The `Series` gap is second, and it costs articulation coverage rather than requirement structure.

One methodological note for whoever reads this next: every gap above was found by reading the build report's exclusion entries, not by testing.
The course-code problem in section 5 was invisible in the demo pair and appeared only at corridor scale, which is the argument for keeping every exclusion individually listed in the committed report rather than summarizing it.
