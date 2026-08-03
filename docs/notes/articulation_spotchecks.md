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

## 7. S9d: the fifteen-campus corridor

Split S9d (2026-08-02) widened `TARGET_IDS` from four receiving campuses to fifteen and removed `MAX_MAJORS_PER_PAIR`.
Sections 1-6 above describe the four-campus artifact and remain accurate for what they measured; this section supersedes their totals.

| | S9c (4 targets, capped at 6) | S9d (15 targets, uncapped) |
|---|---|---|
| Pairs walked | 464 | 1,740 |
| Agreements stored | 2,972, none excluded | 31,236, none excluded |
| Articulations stored | 27,452 | 309,709 |
| Requirement groups stored | 2,278 | 25,039 |
| CC course vocabulary | 6,957 | 15,076 |
| Target course vocabulary | 568 | 1,397 |
| `articulation.db` | 17 MB | 185 MB |

The fetch cost 34,975 requests total (30,827 new) over about 12 hours.
Every one of the 30,827 answered HTTP 200: **zero 429s**, which is the S9c session-renewal rule holding at seven times the scale it was measured at.
Zero pairs hit a `scope_error`; 15 of 1,740 pairs publish no agreement in any year within `YEAR_FALLBACK_DEPTH`.

### Hand verification at NEW campuses

Four campuses that did not exist in the S9c corridor, each checked against the RENDERED agreement on assist.org and then against the built `articulation.db`, not against the API payload.

| Receiving | Sending | Course | assist.org renders | Artifact stores | Result |
|---|---|---|---|---|---|
| CSU Northridge | Merritt College | MATH 105 | (MATH 1 **AND** MATH 50) **OR** (MATH 2 **AND** MATH 50) | `{"any": [{"all": [...]}, {"all": [...]}]}` | match |
| UC Santa Barbara | Mission College | MCDB 1B | (BIO 001A **OR** 001AH) **AND** (BIO 001B **OR** 001BH) | `{"all": [{"any": [...]}, {"any": [...]}]}` | match |
| UC Santa Cruz | Columbia College | CSE 30 | COMP 12P, "Minimum grade required: B or better" | `{"all": [COMP 12P, note]}` | match |
| Cal Poly SLO | Columbia College | CSC 101 | COMP 11P **OR** COMP 11J | `{"any": [...]}` | match |

The UCSB row is the one that matters most: a naive flatten would store `any(001A, 001AH, 001B, 001BH)`, which would tell a student that one honors course alone satisfies a two-course requirement.
The nesting survives, in both directions of the operator (an OR inside an AND, and an AND inside an OR).

### Exclusion rates: read them against the right denominator

The build report files every exclusion under one `articulations_excluded` key, and that conflates two different populations.
`template_shape_unsupported` and `advisement_shape_unknown` remove REQUIREMENT GROUPS; the other three remove ARTICULATIONS.
Dividing all five by stored articulations, as the first draft of this note did, overstates some and understates others.
The two ledgers reconcile exactly, which is the check that they are the right ones:

```
25,039 stored + 87,577 template_shape + 12,741 advisement_shape = 125,357 groups
```

and an independent sweep of the cached payloads counted 125,357 requirement groups.

| Population | Total | Stored | Share |
|---|---|---|---|
| Articulation rows | 359,634 | 309,709 | 86.1% |
| Requirement groups | 125,357 | 25,039 | 20.0% |

| reason_code | Count | Of its own population | S9c |
|---|---|---|---|
| `template_shape_unsupported` | 87,577 | 69.9% of groups | - |
| `advisement_shape_unknown` | 12,741 | 10.2% of groups | - |
| `articulation_type_unsupported` | 49,686 | 13.8% of articulations | 5.88% |
| `mixed_group_conjunction` | 130 | 0.04% of articulations | 0.04% |
| `course_code_unparseable` | 109 | 0.03% of articulations | 0.03% |

(Those figures describe the build BEFORE the two S9d normalizer fixes below; section 10 carries the final ones.)

The jump on `articulation_type_unsupported` is the only one that looks like a regression, and it is not one: it is the four-campus baseline that was unrepresentative.
Per-campus exclusion counts run from UC Berkeley at 8,805 down to UC San Diego at 245, and UCSD plus SJSU - two of the four original targets - are outliers that publish almost pure course-to-course agreements.
UCLA was already at 16.5% non-`Course` inside the S9c baseline.
The breakdown is `Series` 42,428, `Requirement` 4,081, `GeneralEducation` 3,040, `Transferability` 115: all four are genuinely not course-to-course mappings, and `GeneralEducation`, `Transferability` and the `CALGETC` row cell are shapes the four-campus corridor never published at all.
Each was caught by the existing typed exclusion and reported rather than crashing the build, which is the fault-isolation axiom doing exactly its job on data it had never seen.

`course_code_unparseable` stays below the level that would signal a regex gap opened by new data.
Its 109 instances have three causes: 34 payloads with genuinely null `prefix` and `courseNumber`, plus two real shapes the S9c regex does not admit - `ENGL 1AMCH` (the trailing-suffix clause caps at three characters; "AMCH" is four) and `FAM &CS 021` (prefix tokens must start `[A-Z]`; "&CS" starts with `&`).
Both are one-token widenings, both are deferred, and both are recorded here so the next widening starts from evidence rather than from a fresh corridor sweep.

## 8. Correction to section 6: `Following` is not an N-from instruction

Section 6 groups `Following` with `NFromConjunction` and `NFromArea` as "select N from these is unmodeled".
The fifteen-campus data shows that is wrong, and it matters because `Following` is the single largest exclusion category in the artifact.

Across the corridor, group `instruction.type` breaks down as `Following` 31.0%, null 24.3%, `NFromArea` 19.1%, `NFromConjunction` 13.8%, `Conjunction` 11.7%, with `NFromFollowing` and `NToNFromConjunction` negligible.
Only null and `Conjunction` are supported, so roughly 69% of all requirement groups are dropped.

A `Following` instruction carries exactly three keys, in all 3,565 observed instances:

```json
{"type": "Following", "id": "<guid>", "selectionType": "Complete"}
```

No `amount`, no `conjunction`, no selection semantics of any kind.
assist.org renders it as "Complete the following", against "Complete 8.00 semester units from the following" for `NFromArea` and "Complete 1 course from the following." for `NFromConjunction`.
Both the payload and the rendered prose therefore say the same thing: complete all of these, which is precisely what `instruction: null` already means and what the normalizer already maps to conjunction `"And"`.
3,561 of the 3,565 are `selectionType: "Complete"`; the 4 that are `"Select"` are genuinely ambiguous and should stay excluded.

So the largest exclusion category needs no new contract field and no new evaluator semantics.
It fails in the dangerous direction: an excluded group contributes nothing to "requirements still owed", so the triage under-reports what a student owes rather than over-reporting it.

This was fully present in the committed S9c artifact - 3,181 of the 3,565 instances are at the four original targets - so it is a pre-existing gap that S9d measured, not S9d fallout.
Left unchanged in S9d because mapping it is a semantic change to a doc-locked normalizer that materially changes artifact content; it is the strongest candidate for the next increment, ahead of the true N-from family.

## 9. Minor observations, recorded as examined

- 22 articulations are excluded with the detail "ASSIST sending group items was NoneType, expected a list", filed under `articulation_type_unsupported`. The reason code is a slightly loose fit (it is a shape problem, not a type problem) and the semantics may match the "No Course Articulated" case. 22 of 309,709; noted, not acted on.
- `course_projection_conflicts` rose from 27 to 424, which is the expected consequence of the same course appearing in far more agreements under kept-first policy.
- `institution_kind_unknown` stays at 33, unchanged: the category 5 private institutions.
- Receiving courses carry "Same as CPE 101" cross-listing annotations on some campuses. `visibleCrossListedCourses` is not modelled; it is not an advisement and carries no transfer rule. Named here so it reads as examined rather than missed.
- "This Course is Never Articulated" is a distinct string from "No Course Articulated"; both normalize to `sending_expr = None` through the `noArticulationReason` carry-through.

## 10. The two S9d normalizer fixes, and what they bought

Both were made BEFORE the artifact was committed, deliberately: git stores every binary revision in full, so an artifact-changing fix made afterwards costs a second 35 MB revision in permanent history.

### `Following` -> complete-all (section 8)

| | Before | After |
|---|---|---|
| Requirement groups stored | 25,039 | **55,154** (+120%) |
| Share of all groups stored | 20.0% | **44.0%** |
| `template_shape_unsupported` | 87,577 | 57,462 |

The projection in section 8 was +76%, derived by assuming `Following` groups fail the second gate (bad row shape, or an `NFollowing` advisement) at the same rate as the average supported group.
They do not: they fail it far less often, and the measured gain is +120%.
Recorded because the estimate was wrong in the conservative direction, and the next person estimating a normalizer change should know the two gates are not independent.

The remaining 33,720 N-from groups still need a real "N of these" node in `articulation_expr`.

### Course-code regex

Two shapes admitted, both one-token widenings: a CONTINUATION prefix token may open with `&` (`FAM &CS 021`), and the number's trailing group grew from three characters to four (`ENGL 1AMCH`).
`course_code_unparseable` fell from 109 to **70**, a rate of 0.019% of articulation rows, below the 0.026% S9c baseline.

The honest cost, since doc 00 warns about exactly this: `MATH 1ABCD` was a named invalid fixture and is now legal, because it is structurally identical to the real `ENGL 1AMCH` - one digit followed by four letters - and no length rule separates them.
The guard moved out one place to `MATH 1ABCDE`, and `&FAM CS 021` was added as a new invalid fixture, so the widening gained a guard as well as losing one.

All 36 remaining real failures are ONE family, left unfixed and named here so the next widening starts from evidence: `PEAC ARH1`, `PEAC YOG1`, `PEAC TEN1`, `DANC BAL1` and 14 more - a three-letter activity mnemonic followed by a digit, where the number token admits at most two leading letters.
Closing it is `[A-Z]{0,2}` -> `[A-Z]{0,3}`; it was not done because the rate is already below baseline and each widening costs precision.
The other 34 are payloads with genuinely null course parts, which are correctly excluded and not a regex matter at all.

### The N-from node and `Series`

Both landed in S9d after the `Following` fix, on the same before-the-commit reasoning.

`RequirementGroupAsset` gained `select_at_least: int | None`, pinned to `conjunction = "Or"`.
ASSIST publishes 23 distinct selection-rule parameter combinations and this models ONE: `amountUnitType == "Course"` with `amountQuantifier` of `None` or `AtLeast`.
The exclusions are deliberate and each has a reason (`docs/specs/agreement.schema.md`), the sharpest being `UpTo`, which is an elective CAP rather than a requirement and would invert its own meaning if stored as one.

`Series` became a modelled receiving side: new `ReceivingSeries` contract, and both `Articulation` and `TemplateCell` now carry exactly one of a course or a series.
A series is one requirement satisfied by one sending expression; flattening it per-course would claim each receiving course is independently satisfied when the agreement only promises the sequence.

Combined effect of all four S9d normalizer changes:

| | Session start | Final |
|---|---|---|
| Requirement groups stored | 25,039 (20.0%) | **100,000 (79.8%)** |
| Articulations stored | 309,709 (86.1%) | **352,024 (97.9%)** |
| `template_shape_unsupported` | 87,577 | 11,904 |
| `articulation_type_unsupported` | 49,686 | 7,258 |
| Total exclusions | 150,243 | 32,967 |

Two codes ROSE, and both are gates that were previously unreachable rather than new defects:

- `mixed_group_conjunction` 130 -> 316. All 186 new ones are on `Series` articulations, verified by re-reading the payloads: before S9d those died at the type check and their sending expression was never built at all.
- `advisement_shape_unknown` 12,741 -> 13,453. Groups whose `Series` row cells used to kill them at the cell gate now pass it and reach an `NFollowing` section advisement instead.
  The instruction gate cannot be the mover, because both the old and the new normalizer check the instruction after all advisement lists.
  S9e re-derived the split by simulating the old gate order over all 13,453 currently excluded groups: exactly 12,741 died at the advisement gate before S9d too, and exactly 712 died earlier at the template-shape gates.

The group ledger still reconciles exactly (100,000 + 11,904 + 13,453 = 125,357, the independently swept total), which is what proves the movement is between buckets rather than anything vanishing.

Remaining, and deliberately so: 4,081 `Requirement` and 3,040 `GeneralEducation` articulations, 33,720-odd N-from groups outside the modelled slice, and 36 unparseable codes of which 34 are null-payload and 2 are `PEAC SMLP`, a course "number" with no digit in it at all.

### Final artifact

| | |
|---|---|
| Agreements stored | 31,236, none excluded |
| Articulations stored | 352,024 |
| Requirement groups stored | 100,000 |
| CC course vocabulary | 15,425 |
| Target course vocabulary | 1,608 |
| `data/articulation.db` | 316 MB (gitignored build output) |
| `data/articulation.db.gz` | **35 MB (the committed artifact)** |

The database itself is no longer committed: GitHub hard-rejects files over 100 MB.
`make unpack-data` restores it from the gzip and is the first command to run on a fresh clone; `make build-check` still proves canonical-dump identity from the raw cache.

## 11. S9e verification: the N-from semantics contradict the rendered agreements

Split S9e (2026-08-02) verified the S9d revisions against RENDERED assist.org pages before commit, per the standing rule that reading our own input back proves nothing.
The mechanical gates were all green: `make check` 570 passed and 1 skipped, `make build-check` regenerates identically, the committed gzip restores to a canonical-dump-identical database, and a repack of the built database is byte-identical to the committed gzip.
The ledgers reconcile exactly (articulations 352,024 + 7,258 + 316 + 36 = 359,634; groups 100,000 + 11,904 + 13,453 = 125,357), and both risen codes re-derived to their claimed causes: the 316 `mixed_group_conjunction` exclusions split 186 `Series` / 130 `Course` against the payloads, and the advisement rise splits 12,741/712 exactly as section 10 now records.
The artifact was NOT committed, because the rendered pages contradict what `select_at_least` stores.

### What ASSIST renders for the checked groups

All three agreements are Columbia College -> UCLA, year 76.
The instruction objects are quoted from the cached payloads.

| Agreement, group | Instruction (type, conjunction, quantifier, amount, unit) | Sections x cells | Rendered heading | Stored |
|---|---|---|---|---|
| MIMG B.S., pos 1 | NFromConjunction, Or, None, 1.0, Course | 3 x [3, 4, 4] | "Complete 1 course from A, B, or C" | `("Or", 1)` |
| MIMG B.S., pos 4 | NFromConjunction, Or, None, 1.0, Sequence | 2 x [1, 1] | "Complete 1 sequence from A or B" | excluded (unit) |
| Human Biology B.S., pos 1 | NFromConjunction, Or, None, 1.0, Series | 3 x [3, 4, 4] | "Complete 1 series from A, B, or C" | excluded (unit) |
| Human Biology B.S., pos 2 | NFromConjunction, And, AtLeast, 1.0, Course | 1 x [3] | "Complete at least 1 course from A" | `("Or", 1)` |
| Human Biology B.S., pos 7 | NFromConjunction, And, AtLeast, 2.0, Course | 2 x [20, 0] | "Complete at least 2 courses from A" | excluded (empty section) |
| Computer Science B.S., pos 2 | NFromConjunction, And, None, 1.0, Course | 1 x [2] | "Complete 1 course from A" | `("Or", 1)` |
| Computer Science B.S., pos 5 | NFromConjunction, And, None, 1.0, Course | 2 x [1, 1] | "Complete 1 course from A and B" | excluded (non-course cell) |

The rendering formula is uniform: "Complete [at least] {amount} {amountUnitType}(s) from {section letters joined by the instruction's own conjunction}".
The amount counts the NAMED UNIT, always; it never counts sections.
MIMG position 1 and Human Biology position 1 are the same three math pathways, one published counting courses and one counting series, which shows the unit is data entry rather than a derivable property of the group shape.

### Why the stored node is wrong

`select_at_least` was specified as "complete at least this many of the SECTIONS", and the validator pins it to `conjunction = "Or"`.
Both halves contradict the rendering:

- The amount counts courses, so "Complete 1 course from A" over a section of three courses means any one of the three.
  The stored reading, complete one full section, demands all three: a pick-1-of-N inverted into a complete-all-N.
- The instruction's own `conjunction` ("A and B" against "A, B, or C") is discarded, and the stored `Or` claims a disjunction ASSIST did not publish for the roughly 4,955 stored groups whose payload conjunction is `And`.
- The spec sentence "`Or` with `select_at_least = None` and `Or` with `select_at_least = 1` therefore mean the same thing" is false: a plain `Conjunction`/`Or` group ("Complete A or B") requires one full section, an N-from-1 group requires one course.

Measured in the built artifact: 26,121 of the 100,000 stored groups carry `select_at_least`, 23,016 of them hold at least one multi-cell section where the two readings diverge, and 21,171 are single-section groups (every one multi-cell) where the stored reading is the full inversion.
The failure direction is over-reporting, telling a student they owe a whole pathway when the agreement asks for one course.

### Advisement levels the S9c sweep missed

A full-corridor sweep (31,272 payloads, every key ending in `attributes` or `advisements` with non-empty content) shows the S9c "seven levels" conclusion was an artifact of the 364-payload sample.
Levels currently read: articulation `attributes` and `courseAttributes`, sending-articulation `attributes`, sending group and course `attributes`, template group `attributes` and `advisements`, section `advisements`, cell `attributes`.
Levels carrying real prose that nothing reads, so their text is silently dropped today:

| Unread level | Entries | Sample |
|---|---|---|
| template cell `courseAttributes` | 41,246 | "Minimum grade required: B or better" |
| template row `attributes` | 22,655 | "Minimum grade required: C or better" |
| template section `attributes` | 8,778 | "Course cannot  be dual counted" |
| articulation `seriesAttributes` | 2,935 | "Departmental credit limitation applies; see university department adviser" |
| template cell `seriesAttributes` | 2,884 | same family as above |
| cell `requirementAttributes` | 159 | on `Requirement` cells, whose groups are excluded anyway |
| outer articulation `seriesAttributes` | 6 | dept-model series rows |

`receivingAttributes` is not in the table: it is a container object whose `courseAttributes`/`seriesAttributes` mirror the inner articulation's lists verbatim (65 sampled, 0 differing), so dropping it loses nothing.
The largest two rows are grade minimums, exactly the class of advisement the no-silent-drop axiom exists for, and they predate S9d (course cells have carried unread `courseAttributes` since S8).
The series rows are new S9d surface: series articulations and series cells were stored without reading their `seriesAttributes`.

### `templateOverrides`, an unmodeled mechanism

1,526 of the 31,272 payloads carry `articulation.templateOverrides`: an alternate `sendingArticulation` keyed to template variant ids.
Where an override applies, the stored sending expression may not be the rule the rendered template shows for that major.
Not quantified further in S9e; recorded so the next increment starts from evidence.

### Smaller findings

- `Following` with `selectionType: "Select"` counts 460 in this corridor, not the 4 the S9c-era comment in `normalize.py` recorded (fixed in S9e); all 460 are still correctly excluded.
- `Conjunction` and N-from instructions also publish `selectionType: "Select"` (about 7,500 groups) and are stored without examining it; defensible because they carry their own conjunction or amount where `Following` carries neither, but recorded as unexamined surface.
- `NFromFollowing` carries exactly `{type, id, amount, selectionType}` in all 116 instances, confirming the unit-check skip for it.
- No fractional `Course` amounts exist in the corridor, so treating a non-integral amount as an exclusion has no live cost.
- The committed-artifact size prose in `.gitignore`, the `Makefile`, and the overview doc said ~209 MB / ~25 MB; the built artifact is 319 MB / 35 MB (fixed in S9e).

### Resolution: the S9e fixes and the rebuilt artifact

With the user's go-ahead, S9e replaced `select_at_least` with `select_courses` (spec, contract, normalizer, fixtures, schema, tests) and routed the five unread advisement levels through `advisement_texts`, then rebuilt.

- `select_courses = N` means "complete at least N courses from the union of the group's sections", matching the rendered formula; a satisfied series cell counts as one.
  The rename is deliberate: no consumer of the old field ever shipped, and the new name forces the evaluator increment to read the corrected spec.
- The one live ambiguity, `NFromConjunction` with area conjunction `And` over several sections, became a typed `template_shape_unsupported` exclusion.
  Its measured population in this corridor is ZERO stored groups - every multi-section N-from group in the artifact was `Or`-joined or conjunction-free - so the gate is protective, not costly.
- The rebuilt exclusion ledger is IDENTICAL by reason code to the pre-fix build (13,453 / 11,904 / 7,258 / 316 / 36), which is exactly what a semantics rename plus text-only advisement additions should produce: nothing moved buckets, nothing vanished.
- 48,249 of 100,000 stored groups and 19,149 of 352,024 stored articulations now carry advisement text; UCLA MIMG group 1 stores "Acceptable substitute", "Course recommended to be taken at university", and "Not required for admission" exactly where the rendered page prints them, and all were dropped before.
- Verified against the rendered pages after the rebuild: MIMG group 1 and Human Biology group 2 and Computer Science group 2 all store `("Or", select_courses = 1)`, now meaning what ASSIST renders.

Still open, deliberately: `templateOverrides` (about 1,526 payloads), the `Series`/`Sequence`/unit-denominated N-from remainder, and the evaluator semantics for `select_courses`, which increment 6 must implement as "count satisfied cells across the pool".

| | S9d artifact (not committed) | S9e artifact (committed) |
|---|---|---|
| Agreements stored | 31,236 | 31,236 |
| Articulations stored | 352,024 | 352,024 |
| Requirement groups stored | 100,000 | 100,000 |
| CC course vocabulary | 15,425 | 15,425 |
| Target course vocabulary | 1,608 | 1,608 |
| Groups carrying advisement text | - | 48,249 |
| `data/articulation.db` (gitignored) | 316 MB | 319 MB |
| `data/articulation.db.gz` (committed) | 35 MB | 34.5 MB |

## 12. S10a verification: `templateOverrides` is authoring residue the renderer ignores

Split S10a (2026-08-02) resolved the open `templateOverrides` question from section 11 before implementing the evaluator, because doc 03's hand-verification protocol depends on the stored `sending_expr` being the rule the rendered page shows.
The answer: it always is.
ASSIST's public renderer provably never applies an override, so the artifact as committed already matches the rendered ground truth, and the mechanism is closed as verified-vestigial with the user's 2026-08-02 decision.

### The population, measured against the stored artifact

A full sweep of the raw cache (34,771 files; the 1,526-payload figure from section 11 reproduced exactly) joined against the stored artifact by `(agreement_id, position)`:

| | |
|---|---|
| Stored articulations carrying a non-empty override | 1,689 (0.48% of 352,024) |
| Of those, carrying two overrides | 13 (the rest carry one) |
| Override objects total | 1,702 |
| Override objects whose rule DIFFERS from the default (ids stripped) | 1,366 |
| Differing rows where the default is "No Course Articulated" | 865 |
| Distinct stored agreements affected | 1,520 (4.9% of 31,236) |

The differing rows concentrate at three campuses: CSU Northridge 1,346, CSU Fullerton 14, UC Davis 4.

### Why the renderer cannot apply them: the variant join does not exist

An override is scoped by `variantIds`, a list of GUIDs.
Across every one of the 34,771 cached files, those GUIDs occur at exactly one JSON path: `articulations[].articulation.templateOverrides[].variantIds[]`.
They appear in no template asset, no agreements-list report, and no envelope field, so no payload identifies which variant the fetched major IS, and the applying side of the join is simply absent from the public API surface.

The SPA confirms this from the code side.
A rendered agreement page fetches only the six endpoints the corridor build already caches (verified live with network capture on 2026-08-02): appsettings, institutions, AcademicYears, categories, the agreements list, and the agreement payload itself.
In the app bundle (`main.7ffdf5991193db15.js`), `variantIds` occurs exactly twice, both inside payload-deserialization mappers; no code consumes `templateOverrides` after mapping, and the other three bundles (runtime, polyfills, scripts) never mention either name.

### Rendered confirmation, both directions

| Sending | Receiving, major | Receiving course | Default rule | Override rule | Page renders |
|---|---|---|---|---|---|
| Evergreen Valley College | CSUN, Biology B.S. Cell and Molecular | MATH 255B | No Course Articulated | MATH 072 | **No Course Articulated** |
| El Camino College | CSUN, Psychology B.A. | MATH 140 | STAT C1000 or STAT C1000H or BUS 116 | adds PSYC 109A | **the default three-way Or** |

The Psychology check contains a trap worth recording: PSYC 109A does appear on the rendered page, but as the sending side of a separate `Requirement`-type row ("Other Acceptable Statistics", articulation position 3, its own default rule `SOCI 109A or PSYC 109A`), not inside the MATH 140 row.
A text search that stopped at "PSYC 109A is on the page" would have concluded the override applies; reading the row structure shows it does not.

### Consequence for the evaluator and for hand-verification

The stored `sending_expr` is the rendered rule, everywhere, including all 1,689 override-carrying rows.
Evaluator hand-verification needs no override avoidance, and modeling overrides would make the artifact DISAGREE with what a student sees on assist.org, inverting the citation axiom.
The 865 "default says No Course Articulated, override has a rule" rows are not under-reporting: the rendered page says No Course Articulated too.
