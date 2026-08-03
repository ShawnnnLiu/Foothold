# Foothold UI Mockup Brief (prompt for a Claude Design project)

This file is a self-contained prompt for Claude Design (the Anthropic Labs visual design product).
Paste it, or upload it, as the first message of a brand new Claude Design project.
Everything the design agent needs is in this one file: contest goals, product context, the binding Ascent design system, the screens to mock, and the exact data to render.

## Step 0: styling ground rules

Do not infer a generic style: the "Design system: Ascent" section below is the binding visual language for every screen in this project.
Apply it verbatim (exact hex values, Archivo weights, border and shadow rules), and keep all six screens visually consistent with each other; consistency is itself a judged quality.
There is no frontend code yet, which is exactly why these mockups are being made; this file is the sole source of truth.

## What we are optimizing for (contest judging criteria)

Foothold is an entry in the Stellic Pathfinders challenge (category: Overcoming Obstacles), judged on five equally weighted criteria:

1. Does it solve a real student problem.
2. Is it original.
3. How much could it help students if it scaled.
4. The design and experience.
5. How well it's built.

The mockup directly targets criterion 4, but every screen should also make criteria 1-3 legible at a glance:
show the lost-credit problem (real dollars and units at stake), the originality (transcript in, verdict and petition letter out - not a lookup table), and the scale (every California community college on day one).
Judges may be non-technical; helpfulness must read louder than technical complexity.
The final deliverable is a 2-minute demo video, so design for desktop-first screens that read in seconds.

## Product context

Foothold is a transfer credit navigator for the California community college to UC/CSU corridor.
Transfer students lose on average 43 percent of their credits (GAO-17-574); half of transfer students are Pell recipients, so lost credits are lost aid dollars.

The flow: a student picks their community college, target university, and major; enters their courses (autocomplete chips or pasted transcript); and gets a deterministic triage of their credits against the official ASSIST articulation agreement, plus a grounded draft petition letter for credits at risk.

Core thesis, which the UI must dramatize: **LLMs propose, deterministic infrastructure disposes; the AI never decides what transfers - the articulation agreement does.**
Every verdict carries a citation to the exact agreement line it came from, and citations are always visible.

Foothold is NOT a degree audit, not an advising chatbot, and not a scheduler.
Tone: confident, physical, grounded in official data - never chatbot-cute.

## Design system: Ascent

Climbing energy on chalk and slate.
The transfer is a wall the student is already partway up: verdicts are bold hold-tiles, progress is drawn as elevation, and the layout itself steps - each row terraced like a route.
The 3-second read: you're already most of the way up - the next hold is marked.

### Colors

| Token | Hex | Role |
| --- | --- | --- |
| chalk | `#F3F1EC` | page ground |
| slate | `#272B31` | ink: text, borders, shadows |
| hold teal | `#0E8A6D` | cleared verdict (transfers clean) |
| hold amber | `#D97706` | at-risk verdict |
| hold red | `#B3372E` | no-articulation verdict |

### Typography

Archivo everywhere.

- Headings: 900, uppercase.
- Body: 400; emphasis 500.
- Course codes: 800.

### Surface

- 4px corner radius.
- Hard 2px slate borders.
- Flat offset shadows `4px 4px 0` slate - blocky, no blur anywhere.

### Components

**Hold-tile (verdict marker):** a square tile with an icon, paired with an uppercase label.
Shape + icon + word, never color alone - this is an accessibility rule, not a suggestion.

| Verdict | Color | Icon | Label | Treatment |
| --- | --- | --- | --- | --- |
| transfers clean | teal | check | TRANSFERS CLEAN | filled tile, solid border |
| at risk | amber | ! | AT RISK | filled tile, solid border; its row juts out with an amber offset shadow |
| no articulation | red | x | NO ARTICULATION | filled tile, solid border |
| still owed | none (chalk fill) | up-arrow | STILL OWED | outline-only tile, 2px dashed slate border - "route ahead" |

**Terracing:** stacked rows stagger with increasing indent, like steps up a wall; the AT RISK row juts out beyond the terrace line.

**Elevation chart:** progress rendered as ascending filled steps, the final step dashed (unclimbed rock), with an honest `N of M units` figure next to any percentage caption.

**Citations:** uppercase, with a highlighter underline in the verdict's hold color, e.g. `AGREEMENT 2025-2026 - ARTICULATION #5`.

**Wordmark:** FOOTHOLD in Archivo 900 with a three-step ascending mark (the elevation motif at logo scale).

### Motion (design the resting state first; motion is a layer)

Staggered row entrance bottom-up; elevation steps fill sequentially with a count-up on unit and dollar totals; offset shadows lift on hover; the petition button presses into its shadow on click.
All motion is decorative only and disabled under prefers-reduced-motion.

## Screens to mock (priority order)

1. **Triage board (the hero screen - spend the most effort here).**
   Header: student context line ("De Anza College -> UC San Diego - Computer Science, B.S. - Agreement year 2025-2026"), the elevation chart, and unit/dollar totals.
   Body: terraced verdict rows (clean, at risk, no articulation), each row a list of course cards with hold-tiles and citations; the at-risk row juts out.
   A STILL OWED panel in the dashed "route ahead" style.
   A prominent "DRAFT PETITION LETTER" button.
2. **Landing.** Headline "Don't lose the credits you already earned."; three pickers (community college, target university, major); the FOOTHOLD wordmark; one line of the GAO stat as social proof.
3. **Course entry.** Autocomplete chip input (primary), a paste-transcript textarea (secondary), and a "try a sample transcript" button.
4. **Evaluation theater.** A full-screen deterministic progress moment: checks ticking ("resolved 24 of 25 courses... evaluated 61 articulations... checked 12 advisements") rendered as elevation steps filling.
5. **Petition drawer.** A right-side drawer over the triage board: checkboxes on at-risk/lost items, the generated letter with citations visibly underlined in hold colors, a copy button, and a "verify with your counselor" disclaimer line.
6. **Arbitrage tab.** "Take it at a community college instead": ranked list of CC courses that articulate back to a degree, each with dollars saved and its citation.

## Data to render (from the planned architecture's demo fixture)

Use exactly this data in the mockups; it is the shape the real backend produces.
Demo student: 7 resolved courses at De Anza College, evaluating against UC San Diego, Computer Science, B.S., agreement year 2025-2026.

### Header totals

| Metric | Value |
| --- | --- |
| Transfers clean | 5.0 units |
| At risk | 24.5 units (~$2,450) |
| No articulation | 5.0 units (~$500) |
| Still owed | 4.0 units |

Elevation chart composition: total evaluated 34.5 units; 5.0 filled teal (secure), 24.5 as amber outlined steps (within reach via petition), the still-owed 4.0 as the dashed final step.
Suggested caption: "5 of 34.5 units secure - 24.5 more within reach."
Dollar figures are illustrative sample data for the mockup.

### TRANSFERS CLEAN (teal row)

| Your course | Articulates to | Units | Citation |
| --- | --- | --- | --- |
| MATH 1A Calculus I | MATH 20A Calculus for Science and Engineering | 5.0 | Major agreement 2025-2026, articulation #5 |

### AT RISK (amber row, juts out)

| Your course | Articulates to | Units | Reason | Citation |
| --- | --- | --- | --- | --- |
| MATH 1B Calculus II | MATH 20B Calculus for Science and Engineering | 5.0 | Advisement: "Must complete entire series" | Major agreement 2025-2026, articulation #1 |
| MATH 2A Differential Equations | MATH 20D Intro to Differential Equations | 5.0 | Double-count risk: also applied on the department agreement | Major agreement 2025-2026, articulation #0 |
| CIS 22C Data Abstraction and Structures | CSE 12 Basic Data Structures and OO Design | 4.5 | Fuzzy match: resolved by title similarity, not exact code | Major agreement 2025-2026, articulation #7 |
| MATH 1C Calculus III | MATH 20E Vector Calculus | 5.0 | Partial series: MATH 1D still needed | Major agreement 2025-2026, articulation #3 |
| MATH 22 Discrete Mathematics | MATH 15A Discrete Mathematics | 5.0 | Stale year: cited agreement is 2024-2025; newest is 2025-2026 | Department agreement 2024-2025, articulation #4 |
| PHYS 4A (unresolved) | - | - | Not found in the De Anza course list for this year; fix the chip | no citation |

Each at-risk card shows its typed reason as a short plain-English tag; the reason vocabulary is exactly: advisement note, double-count risk, fuzzy match, partial series, stale year, unresolved.

### NO ARTICULATION (red row)

| Your course | Units | Note |
| --- | --- | --- |
| MATH 12 Introductory Calculus for Business and Social Science | 5.0 | No published articulation applies this course to this major |

### STILL OWED (dashed panel)

| Requirement | Units | Citation |
| --- | --- | --- |
| CSE 15L or CSE 29 | 4.0 | Major agreement 2025-2026, articulation #0 |

### Petition drawer sample content

Selected items: MATH 1B (advisement), MATH 1C (partial series), MATH 12 (no articulation).
Letter opening, to show the citation styling: "I am writing to petition for transfer credit for MATH 1B (Calculus II, 5.0 units), which articulates to MATH 20B under the 2025-2026 De Anza College - UC San Diego articulation agreement, articulation #1..."
Every course code and citation in the letter gets the highlighter underline in its verdict's hold color.
Below the letter: a copy button and the line "This is a draft - verify with your counselor before submitting."

### Arbitrage tab sample rows (illustrative sample data)

| Take at De Anza | Counts as at UCSD | Units | You save | Citation |
| --- | --- | --- | --- | --- |
| CIS 22A Python Programming | CSE 8A Intro to Programming | 4.5 | $2,043 | Major agreement 2025-2026, articulation #6 |
| MATH 1D Calculus IV | MATH 20E Vector Calculus (with MATH 1C) | 5.0 | $2,270 | Major agreement 2025-2026, articulation #3 |

## Hard rules

- Never encode a verdict in color alone; always shape + icon + word.
- Every verdict and every letter citation shows its agreement citation; no citation, no claim.
- Counts are honest: always `N of M`, never a lone percentage.
- No blur, no gradients, no rounded-blob softness; the language is blocky, physical, high-contrast.
- Desktop-first (demo video), but the triage board should have a plausible narrow-viewport stacking.
