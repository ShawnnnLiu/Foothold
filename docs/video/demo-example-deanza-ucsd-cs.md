# Demo Video Example: De Anza -> UCSD Computer Science

A verified, real-data student example for the demo video.
Every articulation fact below was verified live against the assist.org API on 2026-08-06 and matches the committed `articulation.db` exactly.
Every dollar figure comes from the schools' own published pages, read the same day.

## Provenance

- ASSIST agreement: De Anza College -> UC San Diego, "CSE: Computer Science B.S.", academic year 2025-2026, published 2026-06-08.
- Agreement key: `76/113/to/7/Major/76ab1c59-2dcf-4c6f-f364-08ddd3b241a4` (major-key GUIDs drift across ASSIST rebuilds; re-resolve by label if refetching).
- ASSIST UI link for screenshots:
  <https://assist.org/transfer/results?year=76&institution=113&agreement=7&agreementType=to&view=agreement&viewBy=major&viewSendingAgreements=false&viewByKey=76%2F113%2Fto%2F7%2FMajor%2F76ab1c59-2dcf-4c6f-f364-08ddd3b241a4>
- De Anza fees: <https://www.deanza.edu/cashier/fees_glance.html> ($31/unit CA resident, $62.75/quarter basic fees).
- UCSD costs: <https://fas.ucsd.edu/cost-of-attendance/undergraduates/index.html> (2026 cohort, 2026-27 table).
- The ASSIST API requires a session bootstrap: `GET /` sets the `X-XSRF-TOKEN` cookie, which every API request echoes as a header (see `backend/src/starmap/assist/fetch.py`).

## The Student

Maya Torres (fictional name, real data): second-year De Anza College student, transferring Fall 2026 to UC San Diego, CSE: Computer Science B.S.
She followed De Anza's standard C++ chain (CIS 22A -> 22B -> 22C) plus the CIS 21J assembly pair, and finished calculus, linear algebra, discrete math, and physics.
Total: 61.5 De Anza units.
She assumes she is done with lower-division CS.

## What Transfers Cleanly (verified)

| De Anza course | Units | UCSD articulation |
|---|---|---|
| MATH 1A, 1B, 1C, 1D (Calculus I-IV) | 20 | MATH 20A, 20B, 20C |
| MATH 2B Linear Algebra | 5 | MATH 18 |
| MATH 22 Discrete Mathematics | 5 | CSE 20 |
| PHYS 4A, 4B | 12 | PHYS 2A, 2B |
| CIS 22C Data Abstraction and Structures | 4.5 | CSE 12 |

## The Three Traps (verified)

1. **CSE 11 only articulates from the Java path** (CIS 35A or CIS 36B).
   Her C++ intro courses CIS 22A and CIS 22B (9 units) articulate to nothing in this agreement.
2. **CSE 30 is a three-course AND-bundle**: CIS 21JA + CIS 21JB + CIS 26B (13.5 De Anza units for one 4-unit UCSD course).
   She took 21JA + 21JB but not 26B, so the partial series grants nothing (9 more units at risk).
3. **CSE 21 and CSE 29 are required but have no De Anza articulation at all** ("no course articulated").
   No De Anza student can complete them before transfer.

## Consequence

Maya arrives at UCSD owing CSE 11, CSE 30, CSE 21, and CSE 29: 16 units of lower-division CSE, all prerequisites gating upper-division courses.
That is a full quarter of coursework, pushing graduation out by at least one quarter.

## The Dollars (real, 2026-27)

- De Anza CA resident: $31/unit enrollment fee, $62.75/quarter basic fees.
- UCSD CA resident tuition and fees 2026-27: $21,519/yr (includes one-time $225 Enrollment Services Fee); on-campus annual cost of attendance $47,283.
- One extra UCSD quarter: **$15,686** (= ($47,283 - $225) / 3).
- De Anza units that bought nothing (CIS 22A, 22B, 21JA, 21JB = 18 units x $31): **$558**.
- **Total exposure: $16,244.**

## The Counterfactual (the demo money shot)

Caught before transfer, the fix is CIS 35A (satisfies CSE 11; she already knows how to program) plus CIS 26B (completes the CSE 30 series).
That is 9 units x $31 = $279, roughly $342 with one quarter of basic fees.
A ~$342 course correction at De Anza versus a $15,686 extra quarter at UCSD is a ~46x difference.
Only CSE 21 and CSE 29, which are structurally impossible from De Anza, remain for after transfer.

## Honest Caveat (say it in the video)

CIS 22A and 22B are not worthless in general: they can serve electives or other majors' agreements.
They are worthless for this major's articulation.
That is exactly the "at risk / no articulation" distinction Foothold's triage draws.
