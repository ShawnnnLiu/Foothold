# Increment F3: The Screens, Wired End to End

Goal: the four deterministic-path screens (landing, course entry, evaluation theater, triage board) rendering the Ascent design against the live doc-01 API, so the demo flow runs pick -> chips -> evaluate -> board on real data.
Binding references: `docs/design/ASCENT.md` (visual spec), `docs/design/triage-board/Foothold Prototype.dc.html` + `support.js` (layout, spacing, copy, and interaction reference; translate its inline styles into the component CSS), the locked design-translation rules in `00-overview.md`, and the screen list in `docs/FOOTHOLD_PATHFINDERS_PLAN.md:199-216`.

No new dependencies.
Screens and components stay thin: no logic beyond calling `lib/` functions and mapping view-model fields to elements; anything conditional beyond a ternary belongs in `lib/`.
Components have no tests (`AGENTS.md`); the manual E2E gate at the end is the verification.

## App shell and navigation (locked)

- No router; `App.tsx` holds a screen state machine exactly like the prototype: `screen: "landing" | "entry" | "theater" | "triage"`, plus the route context `{ sending, receiving, majorKey }`, the chip state, and the current `Evaluation | null`.
- Deep links are out of scope for v1 (the SPA catch-all serves the shell; every visit starts at landing).
- All server calls go through `lib/client.ts`; every fetch error or non-2xx renders a slate banner with the `error_body.error` text and a retry affordance; nothing fails silently.

## Components (exact list)

| Component | Used by | Notes |
| --- | --- | --- |
| `Wordmark` | all screens | three-step ascending SVG mark + FOOTHOLD, Archivo 900, per `ASCENT.md`; the SVG rect geometry is copied from the prototype |
| `FoilButton` | landing, entry, triage sidebar | the doc-00 foil exception: Gold finish, Prism lines texture, pointer-driven sheen (translate `applyFoil` + the `mousemove` handler from `support.js`, DROPPING the `Math.random()` idle-flash loop entirely); falls back to flat slate-on-chalk if the ASCENT amendment is declined at kickoff |
| `HoldTile` | board, sidebar, theater | verdict tile: square, icon + color per the `ASCENT.md` verdict table; `still_owed` variant is dashed outline, chalk fill |
| `CitationTag` | cards, still-owed panel | uppercase text with highlighter underline (`box-shadow: inset 0 -6px 0 <hold color at ~35% alpha>`), text from `format.citationLabel` |
| `ReasonTag` | at-risk cards | bordered pill, text from the doc-02 reason map |
| `WallChart` | triage sidebar, theater | renders `wallSteps(header)`: teal filled / amber OUTLINED (doc-00 rule 3) / dashed steps, staggered left-margin ascent |
| `CourseCard` | board rows | one finding: codes 800-weight, title, arrow, units, `CitationTag`, optional `ReasonTag` + advisement text |

## Screen 1: Landing

- Prototype section `data-screen-label="Landing"` is the layout truth: centered wordmark, headline "Don't lose the credits you already earned.", sub-line, three labeled pickers, foil CTA "Check my credits", the GAO stat line with amber highlighter underline, and the scale line.
- Pickers are native `<select>` styled per the prototype, fed live: CC list from `GET /api/institutions?kind=cc`, target list from `kind=target`, majors from `GET /api/pairs/{s}/{r}/majors` fetched whenever both ids are set (picker disabled with placeholder "PICK BOTH SCHOOLS FIRST" until then).
- CTA disabled until all three picks exist; on click, store the route context and go to entry.
- The agreement-year line under the stat renders the majors response's `year_label`, not a literal.

## Screen 2: Course entry

- Prototype section `data-screen-label="Course entry"`: header bar (wordmark, route context line, "CHANGE ROUTE" back link), chip box, suggestion dropdown, sample button, count line, evaluate CTA, paste block.
- Chips are `lib/courses.ts` state; the input drives `GET /api/cc/{sending}/courses?q=` debounced 150 ms, suggestions rendered in server order (max 8), Enter accepts the first, backspace on empty input pops the last chip.
- "Try a sample transcript" loads the pinned constant `SAMPLE_COURSES` = the nine codes of `data/curated/demo_students/deanza_ucsd_cs.json` (MATH 1A, 1B, 1C, 2A, 2B, 22, CIS 22B, 22C, 36B); each is resolved through the autocomplete API before becoming a chip, so a sample chip is never fabricated client-side.
- Paste block (deterministic v1, doc-00 scope): `extractCourseCodes` over the textarea, each candidate confirmed via the autocomplete API (exact `course_code` match among the hits); confirmed codes become chips, unconfirmed ones are listed under the box as "N not recognized: ..." (no silent drops).
  The LLM parse upgrade replaces this path in doc 05; the UI shape does not change.
- Evaluate CTA (foil) enabled when chips exist; on click go to theater and fire the POST.

## Screen 3: Evaluation theater

- Prototype section `data-screen-label="Evaluation theater"`: the rising step blocks, four check lines, and the closing line "The agreement decides - not the AI".
- The POST to `/api/evaluations` fires on entry; the step animation runs meanwhile; the check lines fill ONLY from the real response (never placeholder numbers):
  line 1 `"Resolved {resolved} of {total} courses"` where `resolved` is `student_courses.length` and `total` adds the count of `unresolved` findings; line 2 `"Evaluated {findings.length} articulation findings"`; line 3 `"Checked {advisement count} advisements"` (findings with non-empty `advisements`); line 4 `"Verdicts locked - agreement year {year_label}"`.
- Minimum display 2.4 s so the moment reads; under `prefers-reduced-motion` (or a failed request) skip the animation entirely; on failure return to entry with the error banner.
- Every timing constant is a literal in the component; no randomness.

## Screen 4: Triage board

- Prototype section `data-screen-label="Triage board"`: slate sidebar (sticky, full height) + chalk board area.
- Sidebar: wordmark, route context, THE WALL (`WallChart` + `wallCaption` lines), the four `HoldTile` totals with `formatUnits`/`formatDollars` (dollar spans omitted when `null`), foil "DRAFT PETITION LETTER" button, and the ground-truth footnote line.
  In this increment the petition button renders disabled with title text "Petition drafting arrives with the letter writer"; doc 05 enables it.
- Board: tab bar (TRIAGE BOARD active; ARBITRAGE tab rendered but disabled until doc 04), then the four terraced rows from `buildTriageBoard`:
  1. TRANSFERS CLEAN: full-width `CourseCard` list, teal header tile, count line `"{n} COURSES · {units} UNITS"`.
  2. AT RISK: the jutting row (amber offset shadow `8px 8px 0 var(--hold-amber)`, extra indent per the prototype), two-column card grid, each card with `ReasonTag`, advisement or detail text, `CitationTag`, units.
  3. NO ARTICULATION: red header tile, full-width cards; the card body renders `finding.detail`.
  4. STILL OWED: dashed panel per `ASCENT.md` "route ahead" treatment, count line `"ROUTE AHEAD · {units} UNITS"`.
- Terrace indents are fixed per-row steps (0, 34, 68, 102 px from the prototype) derived from the row's position in the locked bucket order, never free-form (`ASCENT.md` terracing rule).
- Row entrance stagger and the sidebar count-up translate from the prototype with parameters as pure functions of row index and header totals; both disabled under reduced motion.
- Unresolved findings render in the at-risk grid with the UNRESOLVED tag, "No citation" muted text, and a "fix the chip" hint linking back to entry, exactly like the prototype's PHYS 4A card.
- "EDIT COURSES" returns to entry preserving chips.

## E2E gate (manual, the increment's exit)

Run `make run` + `npm run dev`, walk the full flow with the sample transcript for De Anza -> UC San Diego -> the verified CS major, and check against `docs/notes/evaluator_verification.md`:

- 21 findings distributed 14 clean / 4 partial-series at risk / 1 no-articulation (CIS 22B) / 2 still owed.
- Sidebar units 34.0 / 5.0 / 4.5 / 10.0; dollars ~$1,455 at risk and ~$1,310 lost (rendered from the response, not typed anywhere in the frontend).
- Every card shows its citation; the still-owed panel cites; the unresolved path (add a fake chip is impossible by construction; instead paste text containing an unknown code and confirm it is listed as not recognized).
- `prefers-reduced-motion` walk-through shows every number without animation.
- Also verify `npm run build` output served by the doc-01 SPA mount (visit the FastAPI port directly) renders identically; this proves the catch-all + `no-cache` path.

Per the pixel-perfection standard in the user's global instructions, compare each screen side by side against the prototype at 1440 px wide and fix visible deviations before the increment closes.
