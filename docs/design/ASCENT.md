# Ascent: the Foothold design direction

Status: design spec, docs-only for now; no frontend scaffolding or npm dependencies exist yet.
Authority: subordinate to `docs/FOOTHOLD_PATHFINDERS_PLAN.md`; binding for all frontend styling and view-model presentation work.
Adopted 2026-08-01 as direction 1c ("Ascent") alongside the product rename from Astrolabe to Foothold.

## Concept

Climbing energy on chalk and slate.
The transfer is a wall the student is already partway up: verdicts are bold hold-tiles, progress is drawn as elevation, and the layout itself steps, each row terraced like a route.
Confident, physical, high-contrast; your finished work visibly holds your weight.
The 3-second read: you're already most of the way up - the next hold is marked.

## Palette

| Token | Value | Role |
| --- | --- | --- |
| `--chalk` | `#F3F1EC` | ground / page background |
| `--slate` | `#272B31` | ink: text, borders, shadows |
| `--hold-teal` | `#0E8A6D` | cleared hold: `transfers_clean` |
| `--hold-amber` | `#D97706` | at-risk hold: `at_risk` |
| `--hold-red` | `#B3372E` | no articulation: `no_articulation` |

Color is never the only carrier of meaning; every verdict also reads through shape, icon, and word (see the verdict table below).

## Verdict hold-tiles

A hold-tile is a square tile bearing an icon, paired with an uppercase label.
Shape + icon + word, never color alone.

The `TriageBucket` contract (`docs/specs/reason_codes.schema.md`) has four values; the fourth, `still_owed`, is locked here since the original brief covered only three:

| `TriageBucket` | Color | Icon | Label | Treatment |
| --- | --- | --- | --- | --- |
| `transfers_clean` | teal `#0E8A6D` | check | TRANSFERS CLEAN | filled tile, solid 2px slate border |
| `at_risk` | amber `#D97706` | ! | AT RISK | filled tile, solid 2px slate border; the row juts out with an amber offset shadow |
| `no_articulation` | red `#B3372E` | x | WON'T TRANSFER | filled tile, solid 2px slate border |
| `still_owed` | none (chalk fill) | up-arrow | STILL OWED | "route ahead" style: outline-only tile, 2px dashed slate border, no hold color, echoing the elevation chart's dashed final step |

Plain-language amendment (2026-08-03), user-requested: display copy avoids transfer-office jargon; internal identifiers (`TriageBucket` values, route names, component names) are unchanged.

- The `no_articulation` label is WON'T TRANSFER (was NO ARTICULATION).
- The board tabs are YOUR CREDITS and SAVE MONEY (were TRIAGE BOARD and ARBITRAGE).
- The evaluate CTA is "See what transfers" (was "Evaluate against ASSIST").
- Citation tags read `AGREEMENT LINE #N` (was `ARTICULATION #N`).
- "ASSIST" and "articulation" appear only in fine-print provenance lines (landing footer, triage footnote), never in a control or verdict label.

## Type

Archivo throughout.

- Headings: weight 900, uppercase.
- Body: weight 400, emphasis 500.
- Course codes: weight 800.

Font delivery (self-hosted files vs package) is decided when the frontend is scaffolded, not here.

## Surface

- Corner radius: 4px.
- Borders: hard 2px slate.
- Shadows: flat offset `4px 4px 0` slate, blocky, no blur anywhere.

## Terracing

Rows stagger with increasing indent, like steps up the wall.
The AT RISK row juts out beyond the terrace line with an amber offset shadow, so the row demanding action is physically the most prominent.
Indentation is a fixed per-row step derived from the row's stable sort position, never a free-form offset.

## Elevation chart

The triage header renders progress as elevation: N-of-M units drawn as ascending filled steps, with the final step dashed, captioned like "77% of the climb done" (always alongside the exact `N of M units` figure, per the honest-count rule in `docs/FOOTHOLD_TECH_REFERENCE.md` section 2.7).
It is a pure function of the deterministic triage header totals (clean units over total evaluated units); absent data means the chart is omitted, never fabricated.
Scope note: this deliberately reverses part of the earlier "any atlas/sky visualization" cut; the elevation chart is a small triage summary graphic, not the pre-pivot Mode C pathway atlas, which stays cut.

## Foil CTA exception (amendment, 2026-08-03)

A deliberate, bounded exception to the flat-surface rules above, confirmed by the user at the doc-03 split kickoff per `docs/implementation-plans/frontend/00-overview.md` rule 2.

- Exactly three buttons render as gradient "foil": the landing CTA (Check my credits), the evaluate CTA (See what transfers), and the draft-petition CTA (Draft petition letter).
- The finish is fixed to Gold (`#FDEBBE #EDAD3F #CE8412 #A96606 #EBB856`, ink `#38220A`) with the Prism lines texture; there is no runtime finish switching.
- The sheen is pointer-driven only: every sheen parameter is a pure function of cursor position relative to the button.
  The prototype's PRNG idle-flash loop is dropped entirely, per the determinism axiom (reinstated for the wall pillars only by the third amendment below; foil buttons never flash idle).
- Every other surface stays flat chalk/slate; this exception does not extend to new buttons.

Second amendment (2026-08-03), user-requested with the landing demo button:

- A fourth foil button exists: the landing "Roll a random demo" button, and only it renders the Rainbow finish (holographic hue band, ink `#33203A`), with the same Prism lines texture and pointer-driven sheen.
- The Rainbow finish adds one idle CSS-keyframe drift of the base gradient so the button shines at rest; the drift is a fixed keyframe animation (deterministic, no PRNG) and is disabled under `prefers-reduced-motion`.
- Finishes stay fixed per call site; there is still no runtime finish switching.
- Which demo preset loads is chosen randomly in the click handler; this is event input, not render state, so the deterministic-rendering axiom is untouched (the chosen preset renders deterministically).

Third amendment (2026-08-03), user-requested at the pillar-animation parity pass:

- The wall chart copies the prototype's pillar animations exactly.
  The sidebar wall's sheen loops forever on the prototype's fixed per-step durations and delays, the theater sweep fires once on its fixed per-block timings, and the at-risk steps carry the prototype's holographic sheen layer over their amber-outline chalk fill.
  All of those constants are pure functions of the step's stable position (deterministic).
- The prototype's ambient "chance events" are reinstated verbatim on the triage sidebar wall: a `Math.random()`-timed loop (3.5-9s intervals) plays a single holoflash, a staggered all-step cascade, or a brightness pop on the sheen-bearing steps.
  This is the sole PRNG exception, carved out in the `CLAUDE.md` determinism axiom by explicit user decision: the randomness is presentation-only ambience, never layout, view-model content, or workflow state, and the loop is skipped under `prefers-reduced-motion`.
- Foil buttons are unaffected: their sheen stays pointer-driven only, plus the Rainbow finish's fixed keyframe drift.

## Citations

Every finding's citation (agreement key, articulation position, year) is always rendered, per the citation axiom in `CLAUDE.md`.
Style: uppercase, with a highlighter underline in the verdict's hold color.

## Wordmark

FOOTHOLD set in Archivo 900, with a three-step ascending mark.
The mark is the elevation chart's motif at logo scale: three steps rising left to right.

## Motion (future tier, not v1)

Planned once the frontend exists; none of this gates the static v1:

- Staggered row entrance: rows "step in" bottom-up.
- Elevation steps fill sequentially, with a count-up on the unit and dollar totals.
- Offset shadows lift on hover.
- The appeal (petition) button presses into its shadow on click.

Determinism reconciliation, binding on any implementation:

- Every animation parameter (stagger index, delay, count-up target) is a pure function of the order-stable view-model: stagger index = the row's stable sort position, count-up target = the deterministic total.
- No PRNG anywhere, matching the deterministic-rendering axiom in `CLAUDE.md`.
- Animation is presentation only; it never gates data availability or changes what is rendered.
- Honor `prefers-reduced-motion` by disabling entrance and count-up animation entirely.
