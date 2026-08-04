# Plain-Language Copy Rules

Status: binding for all user-facing copy.
Established by the plain-language pass of 2026-08-03 (PRs #12 and #13); the dated amendment in `ASCENT.md` records the label changes themselves.
This document records the rules behind those changes so future copy follows them without re-deriving the reasoning.

## The core rule

Display copy speaks the student's language, not the transfer office's.
The student's mental model is "which of my credits count, and what will it cost me"; every control, verdict, and headline must be readable in those terms on first sight.
Domain vocabulary (ASSIST, articulation, advisement) is provenance, not interface: it may appear only in fine print, where it proves rigor instead of demanding translation.

## Vocabulary table

Never show the left column in a control, verdict label, tab, CTA, or headline.

| Jargon | Say instead | Notes |
| --- | --- | --- |
| articulation / articulate | transfer, count toward, match | "articulation agreement" becomes "transfer agreement" or "official agreement" |
| ASSIST | the official transfer agreement | "ASSIST.org" is allowed in fine-print provenance lines only |
| triage | check, results, your credits | |
| arbitrage | save money, cheaper credits | name the benefit, not the mechanism |
| evaluate | check, see what transfers | |
| advisement | fine-print condition | |
| owed | needed, left to take | "owed" reads like a debt figure |
| findings | checks, results | |

## Canonical strings

These are the current, agreed labels.
Change them only deliberately, and update this table plus the pinned tests when you do.

| Surface | Copy | Lives in |
| --- | --- | --- |
| Landing tagline | "Foothold checks every course against the official transfer agreement between your two schools - and every verdict cites the exact line it came from." | `frontend/src/lib/landing.ts`, `frontend/src/screens/Picker.tsx` |
| Landing provenance | "Powered by ASSIST.org, California's official transfer database" | `frontend/src/lib/landing.ts`, `frontend/src/screens/Picker.tsx` |
| Landing CTA | "Check my credits →" | `frontend/src/lib/landing.ts`, `frontend/src/screens/Picker.tsx` |
| Landing badge + footer tagline | "Course checks for California transfers" | `frontend/src/lib/landing.ts` |
| Landing method headline + card foot | "The agreement decides - not the AI." | `frontend/src/lib/landing.ts` |
| Landing receipt header lead | "The official agreement · {route}" | `frontend/src/lib/landing.ts` |
| Landing wall caption suffixes | "{honest count} before the check." · "{honest count} - if you fight the flags." | `frontend/src/lib/landing.ts` |
| Landing savings kicker | "Save money" | `frontend/src/lib/landing.ts` |
| Entry CTA | "See what transfers →" | `frontend/src/screens/Entry.tsx` |
| Board tabs | YOUR CREDITS · SAVE MONEY | `frontend/src/screens/Triage.tsx` |
| Verdict labels | TRANSFERS CLEAN · AT RISK · WON'T TRANSFER · STILL NEEDED | `frontend/src/screens/Triage.tsx`, table in `ASCENT.md` |
| Still-needed subtitle | "LEFT TO TAKE FOR THIS MAJOR · N UNITS" | `frontend/src/screens/Triage.tsx` |
| Triage provenance | "Every result comes straight from ASSIST.org, the official California transfer database - each card cites its exact line." | `frontend/src/screens/Triage.tsx` |
| Citation tag | "MAJOR AGREEMENT {year} - AGREEMENT LINE #{n}" | `frontend/src/lib/format.ts` |
| Theater lines | "Resolved N of M courses" / "Ran N checks against the official agreement" / "Flagged N fine-print conditions" / "Verdicts locked - agreement year {year}" | `frontend/src/lib/evaluation.ts` |
| No-citation fallback | "No transfer match published for this course in this major" | `frontend/src/components/CourseCard.tsx` |
| Arbitrage intro | "Courses still open at {college} that count toward this degree - ranked by tuition saved." | `frontend/src/components/ArbitragePanel.tsx` |

## Style rules

- Verdict labels are short parallel phrases in the student's own words (TRANSFERS CLEAN, AT RISK, WON'T TRANSFER, STILL NEEDED), uppercase, never color alone (see the verdict table in `ASCENT.md`).
- Name the benefit, not the mechanism: a tab or button says what the user gets (SAVE MONEY), not what the system does (ARBITRAGE).
- CTAs promise the payoff screen: "See what transfers", "Check my credits".
- Be blunt where the data is final: WON'T TRANSFER is more truthful than a softened "no match", because the petitionable bucket is AT RISK, not this one.
- Provenance is a feature: exactly two fine-print lines (landing footer, triage sidebar footnote) name ASSIST.org, and every card cites its agreement line.
  Do not add ASSIST mentions elsewhere; do not remove these two.
- Handle singular/plural explicitly in any counted string ("1 fine-print condition", "2 fine-print conditions"); never ship "1 conditions".
- Honest counts everywhere, per `docs/FOOTHOLD_TECH_REFERENCE.md` section 2.7: plain wording never replaces or rounds away an exact figure.

## What a copy change may and may not touch

Copy changes are display-only.

- Never rename internal identifiers for wording reasons: `TriageBucket` values (`no_articulation`, `still_owed`), reason codes, route names, component and CSS class names, API fields.
  The contracts in `docs/specs/` are frozen; a label and its identifier are allowed to disagree (`no_articulation` renders as WON'T TRANSFER).
- Pinned-string tests (`format.test.ts`, `evaluation.test.ts`) are part of the change, not an obstacle: update the expectation in the same commit, never loosen the assertion.
- Historical documents (implementation plans, the prototype HTML snapshot in `docs/design/triage-board/`) keep their original wording; they record what was planned, not what ships.

## Checklist for future language changes

1. Sweep for every occurrence first: `grep -rniE "<term>" frontend/src docs/design/ASCENT.md`, including tooltips, empty states, error states, and fallback strings, not just the obvious label.
2. Reword all user-visible occurrences consistently in one pass; a term half-replaced is worse than either wording.
3. Keep verdict-label parallelism and the style rules above.
4. Update the pinned tests in the same commit.
5. Update the canonical-strings table in this document.
6. If a verdict label, tab, CTA, or provenance line changed, extend the dated plain-language amendment in `ASCENT.md`.
7. Run `npx vitest run` and `npm run build` from `frontend/` before committing.
