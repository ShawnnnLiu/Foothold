# ASSIST API Spike Findings

Date: 2026-07-31.
Produced by increment 3 of the pivoted `docs/IMPLEMENTATION_ROADMAP.md`.
Consumed by increments 4 (articulation contracts) and 5 (fetch/normalize/store).
Captured payloads live in `backend/tests/fixtures/assist/` and are the ground truth for contract design.

## Decision

Outcome: `go`, via the legacy same-origin API at `https://www.assist.org/api/*`.

- The next-gen documented API (`prod.assistng.org/apidocs`) returns 401 without an API key; obtaining one routes through help@assist.org and is not needed for our scope.
- The legacy API that the assist.org Angular SPA itself calls is publicly reachable and serves everything the plan needs: institutions, academic years, agreement lists per pair, and full articulation payloads.
- All shapes below were verified against live responses on 2026-07-31.

## Access mechanics (the 400 gotcha)

Bare requests to `https://www.assist.org/api/*` return `{"title":"Bad Request","code":400}`.
The API requires the anti-forgery pair that the SPA uses:

1. `GET https://www.assist.org/` sets a non-HttpOnly cookie named `X-XSRF-TOKEN` (plus an HttpOnly `XSRF-TOKEN` cookie and Azure ARRAffinity cookies).
2. Every API request must send the cookie jar AND echo the `X-XSRF-TOKEN` cookie value as an `X-XSRF-TOKEN` request header.

With that pair, every probed endpoint returned 200 with a browser User-Agent at 1 req/s.
The fetcher must bootstrap a session (fetch `/` once, persist the jar) and refresh it if a 400 reappears mid-run.

## Endpoints (verified)

- `GET /api/AcademicYears`: `[{"id": 76, "fallYear": 2025}, ...]`; id 76 = academic year 2025-2026, the latest with published agreements; ids exist through 79 (fall 2028).
- `GET /api/institutions`: 181 institutions, each `{id, names[], code, isCommunityCollege, category, termType, ...}`.
  `isCommunityCollege: true` marks the sending side (~116 CCs).
  Key ids: De Anza 113, UCSD 7, UCLA 117, UCI 120, SJSU 39, SDSU 26.
- `GET /api/agreements/categories?receivingInstitutionId=&sendingInstitutionId=&academicYearId=`: category codes `major`, `dept`, `prefix`, `breadth` with a `hasReports` flag per pair (breadth was false for De Anza to UCSD).
- `GET /api/agreements?receivingInstitutionId=7&sendingInstitutionId=113&academicYearId=76&categoryCode=major`: `{reports: [{label, key, ownerInstitutionId}], allReports: [...]}`.
  De Anza to UCSD 2025-26 has 168 major reports and 86 department reports.
  The `key` format is `{yearId}/{sendingId}/to/{receivingId}/{Major|Department}/{id}`.
- `GET /api/articulation/Agreements?Key={key}`: the full agreement payload.

Volume check: the plan's corridor estimate holds; one agreement payload is 30-60 KB, and list endpoints are cheap.

## Agreement payload model

Top level: `{result, validationFailure, isSuccessful}`.
`result` fields: `name`, `type`, `publishDate`, `catalogYear`, plus `receivingInstitution`, `sendingInstitution`, `academicYear`, `templateAssets`, `articulations`, which are all JSON-STRINGIFIED STRINGS that must be `json.loads`-ed a second time.
Normalization must treat this double decoding as a first-class stage with typed failure.

Two articulation list shapes, matching the official docs' two models:

- Major agreements (template-cell model): `articulations` is a list of `{templateCellId, receivingAttributes, articulation}`.
- Department agreements (base model): `articulations` is a list of bare articulation objects.

The inner articulation object is identical in both:

- `type`: `"Course"` in all captured entries; `"Series"` and requirement types exist in the wild and the contract must tolerate unknown types by exclusion, not crash.
- Receiving side: `course` with `{prefix, courseNumber, courseTitle, minUnits, maxUnits, courseIdentifierParentId, begin, end, pathways[]}`.
- `sendingArticulation`: the transfer rule:
  - `items`: a list of course groups; each group has `courseConjunction` (`"And"`/`"Or"`) over its `items` (courses with prefix/number/title/units).
  - `courseGroupConjunctions`: conjunctions BETWEEN groups by position (`groupConjunction`, `sendingCourseGroupBeginPosition`, `sendingCourseGroupEndPosition`); observed value `"Or"`.
  - Empty `items` means "No Course Articulated" (observed on UCSD MATH 10B/10C from De Anza); `noArticulationReason` may carry text and was null in captures.
  - `attributes` lists exist at articulation, sending-articulation, group, and course levels; empty in the captured pair but they are the advisement carrier and map to `note` leaves.
- This maps directly onto the `articulation_expr` all/any tree: groups become `all` or `any` nodes per `courseConjunction`, group conjunctions join them (observed `Or` = any-of-groups), attributes become `note` leaves.

`templateAssets` (major agreements only, also double-encoded) is the still-owed structure: typed assets `GeneralTitle`, `GeneralText`, `RequirementGroup`; groups contain `sections` of cells referencing `templateCellId`, and `instruction` objects carry conjunction/selection semantics (e.g. `{"type": "Conjunction", "conjunction": "Or", "selectionType": "Select"}`).
Requirement evaluation for `still_owed` walks template assets and checks whether each referenced cell's articulation was satisfied.

## Terms of use

The terms are rendered by the SPA (embedded in the bundle), authored by UCOP.
Findings from the embedded text: UC Regents and partners claim copyright over site content; conduct clauses forbid harvesting information about other USERS (e-mail addresses etc.), damaging operation, and unlawful use; no clause addresses automated read access to articulation data.
Assessment: polite (1 req/s), cached, non-commercial contest use with visible attribution ("Data: ASSIST.org, the official California articulation repository") is defensible; if the project outgrows the contest, request an official data extract via help@assist.org (the documented channel).

## Implications for increments 4 and 5

1. The fetcher needs session bootstrap (cookie jar + `X-XSRF-TOKEN` echo) and 400-triggered session refresh; everything else is plain GET.
2. Normalization is two-stage: envelope decode (`result`, `isSuccessful`), then per-field `json.loads` of the five stringified fields, each with typed failure and per-agreement fault isolation.
3. Contracts must model both articulation list shapes (template-cell wrapper vs bare) over one shared inner articulation contract.
4. Unknown `type` values and non-Course receiving sides are excluded with a typed reason and counted in the build report, never fatal.
5. `isCommunityCollege` from `/api/institutions` is the authoritative sending-side filter; no hand-curated CC list needed.
6. Latest published year is discovered per pair via `hasReports`/report presence, not assumed globally; record the year id on every stored agreement.
7. The fixtures in `backend/tests/fixtures/assist/` cover: both list shapes, both agreement models, a no-articulation cell, honors-vs-regular `Or` groups, and a multi-course `And` group (MATH 1C + 1D to MATH 20E).
   Advisement `attributes` content is NOT yet covered; capture one advisement-bearing agreement during increment 5's first corridor fetch and add it as a fixture.
