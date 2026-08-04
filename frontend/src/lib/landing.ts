// The marketing landing page's content model: every display string the
// Landing screen renders, built here (React-free) so the pinned tests in
// landing.test.ts can hold the copy to docs/design/PLAIN_LANGUAGE.md.
// Layout truth is docs/design/triage-board/Foothold Landing.dc.html; the
// export predates the plain-language pass, so where its wording is stale the
// strings here follow the canonical table and the shipped code instead.
// Derived strings (citations, count lines, dollars, the wall caption) reuse
// format.ts so the illustrations can never drift from the real product.

import type { Citation, EvaluationFindingCode } from "./api";
import type { TriageHeader, WallStep } from "./evaluation";
import { citationLabel, countLine, formatDollars, formatUnits, wallCaption } from "./format";

// The one route every illustration on the page depicts.
export const DEMO_YEAR = "2025-2026";
const DEMO_MAJOR_CITATION = (position: number): Citation => ({
  assist_key: `${DEMO_YEAR}/Major/demo`,
  position,
  year_label: DEMO_YEAR,
});

export const NAV_LINKS = [
  { label: "Method", href: "#method" },
  { label: "Petitions", href: "#petitions" },
  { label: "Savings", href: "#savings" },
] as const;

// "Course triage for California transfers" in the export; "triage" never
// shows outside fine print (PLAIN_LANGUAGE.md vocabulary table).
export const BADGE = "Course checks for California transfers";

export const HERO = {
  headline: "Don't lose the credits you already earned.",
  // The canonical landing tagline, exactly (PLAIN_LANGUAGE.md).
  tagline:
    "Foothold checks every course against the official transfer agreement between your two " +
    "schools - and every verdict cites the exact line it came from.",
  cta: "Check my credits →",
  navCta: "Check my credits",
  secondaryCta: "See the method",
} as const;

export interface MockRow {
  bucket: "transfers_clean" | "at_risk" | "no_articulation";
  label: string;
  countLine: string;
  cards: MockCard[];
}

export interface MockCard {
  code: string;
  title: string;
  target?: string;
  targetTitle?: string;
  reasonCode?: EvaluationFindingCode;
  reasonNote?: string;
  citation?: Citation;
  fallback?: string;
  units?: string;
}

export const MOCKUP = {
  routeLine: `De Anza College → UC San Diego · Computer Science, B.S. · ${DEMO_YEAR}`,
  tabs: ["YOUR CREDITS", "SAVE MONEY"],
  rows: [
    {
      bucket: "transfers_clean",
      label: "TRANSFERS CLEAN",
      countLine: countLine(1, 5),
      cards: [
        {
          code: "MATH 1A",
          title: "Calculus I",
          target: "→ MATH 20A",
          targetTitle: "Calculus for Science and Engineering",
          citation: DEMO_MAJOR_CITATION(5),
          units: `${formatUnits(5)} U`,
        },
      ],
    },
    {
      bucket: "at_risk",
      label: "AT RISK",
      countLine: `${countLine(6, 24.5)} · ${formatDollars(2450)} AT STAKE`,
      cards: [
        {
          code: "MATH 1B",
          title: "Calculus II",
          target: "→ MATH 20B",
          reasonCode: "advisement_note",
          reasonNote: '"Must complete entire series"',
        },
        {
          code: "CIS 22C",
          title: "Data Structures",
          target: "→ CSE 12",
          reasonCode: "fuzzy_match",
          reasonNote: "Resolved by title similarity",
        },
      ],
    },
    {
      bucket: "no_articulation",
      label: "WON'T TRANSFER",
      countLine: `${countLine(1, 5)} · ${formatDollars(500)}`,
      cards: [
        {
          code: "MATH 12",
          title: "Introductory Calculus for Business",
          // The canonical no-citation fallback (PLAIN_LANGUAGE.md).
          fallback: "No transfer match published for this course in this major",
          units: `${formatUnits(5)} U`,
        },
      ],
    },
  ] as MockRow[],
} as const;

export const PROOF = {
  label: "Every California community college on day one",
  colleges: [
    "De Anza College",
    "Foothill College",
    "Diablo Valley",
    "Santa Monica College",
    "Pasadena City",
    "Ohlone College",
  ],
} as const;

export const CITATIONS_SECTION = {
  kicker: "Citations",
  headline: "Every verdict shows its receipt.",
  body:
    "No black box. Each card cites the agreement year and the exact agreement line it came " +
    "from, so you - and your counselor - can check Foothold's work against the source.",
  link: "See a verdict card →",
  card: {
    code: "MATH 22",
    title: "Discrete Mathematics",
    target: "→ MATH 15A",
    reasonCode: "stale_year" as EvaluationFindingCode,
    reasonNote: `Cited 2024-2025; newest is ${DEMO_YEAR}`,
    citation: citationLabel(
      { assist_key: "2024-2025/Dept/demo", position: 4, year_label: "2024-2025" },
      "demo",
    ),
  },
  receipt: {
    header: "The official agreement · De Anza → UC San Diego · CS B.S.",
    lead: "Agreement line #4 - ",
    quote: "MATH 15A Introduction to Discrete Mathematics ⇐ MATH 22 Discrete Mathematics (5.0)",
    verified: "Verified against the published agreement line",
  },
} as const;

export const METHOD_SECTION = {
  kicker: "Method",
  headline: "The agreement decides - not the AI.",
  body:
    "Foothold checks your courses against the official transfer agreement, line by line. " +
    "Language models help read messy transcripts; they never rule on your credits. Every " +
    "outcome is reproducible from the source agreement.",
  // The evaluation theater's four check lines (lib/evaluation.ts
  // theaterLines) with the demo route's counts; the third is the amber flag.
  steps: [
    { flag: false, label: "Resolved 8 of 8 courses" },
    { flag: false, label: "Ran 14 checks against the official agreement" },
    { flag: true, label: "Flagged 6 fine-print conditions" },
    { flag: false, label: `Verdicts locked - agreement year ${DEMO_YEAR}` },
  ],
  cardFoot: "The agreement decides - not the AI",
} as const;

export const PETITIONS_SECTION = {
  kicker: "Petitions",
  headline: "Flags become appeals in one click.",
  body:
    "Check the flags you want to fight and Foothold drafts a petition letter grounded in the " +
    "agreement - every claim cited to its agreement line, ready to send to the admissions " +
    "office.",
  link: "Draft a letter →",
  flags: [
    { code: "MATH 1B", title: "Calculus II", reasonCode: "advisement_note" },
    { code: "MATH 22", title: "Discrete Mathematics", reasonCode: "stale_year" },
  ] as { code: string; title: string; reasonCode: EvaluationFindingCode }[],
  draftHeader: `Draft - grounded in the ${DEMO_YEAR} agreement`,
  copyButton: "Copy letter",
} as const;

// The letter excerpt depicts real product output addressed to an admissions
// office, so it keeps the official vocabulary on purpose; landing.test.ts
// exempts it from the display-copy jargon lint.
export const LETTER = {
  salutation: "To the Office of Admissions, UC San Diego:",
  body: [
    "I completed ",
    "MATH 22",
    " (Discrete Mathematics, 5.0 units), which articulates to ",
    "MATH 15A",
    " under ",
    "the 2024-2025 department agreement - agreement line #4",
    `. I request confirmation that the articulation carries into the ${DEMO_YEAR} agreement year…`,
  ],
} as const;

// The wall depicts the mockup's totals (5 clean + 24.5 at risk + 5 still
// needed); the caption reuses the product's honest-count formatter.
const STAKES_HEADER: TriageHeader = {
  clean_units: 5,
  at_risk_units: 24.5,
  no_articulation_units: 5,
  still_owed_units: 5,
  at_risk_dollars: 2450,
  no_articulation_dollars: 500,
  course_count: 8,
  finding_count: 14,
};

const STAKES_CAPTION = wallCaption(STAKES_HEADER);

export const STAKES_SECTION = {
  kicker: "The stakes",
  stat: "43%",
  headline: "of credits are lost by the average transfer student.",
  body:
    "U.S. Government Accountability Office, GAO-17-574. At California tuition rates, that's " +
    "semesters of work - and thousands of dollars - evaporating in the transfer.",
  wallTitle: "THE WALL - YOUR ROUTE, UNIT BY UNIT",
  captionTop: `${STAKES_CAPTION[0]} before the check.`,
  captionBottom: `${STAKES_CAPTION[1]} - if you fight the flags.`,
} as const;

// One secure step, four within reach, the last still needed - the export's
// six fixed steps. Rendered by WallChart's landing variant, which carries the
// fixed sheen loops but never the triage sidebar's PRNG chance events.
export const STAKES_WALL_STEPS: WallStep[] = [
  { kind: "secure" },
  { kind: "reach" },
  { kind: "reach" },
  { kind: "reach" },
  { kind: "reach" },
  { kind: "owed" },
];

export const SAVINGS_SECTION = {
  kicker: "Save money",
  headline: "Finish the route for less.",
  body:
    "Foothold finds courses still open at your community college that count toward your " +
    "target degree - ranked by tuition saved, each with its citation.",
  cards: [
    {
      rank: "#1",
      code: "MATH 1D",
      title: "Calculus IV",
      target: "→ MATH 20E",
      targetTitle: "Vector Calculus",
      citation: DEMO_MAJOR_CITATION(3),
      savings: formatDollars(2270) as string,
    },
    {
      rank: "#2",
      code: "CIS 22A",
      title: "Python Programming",
      target: "→ CSE 8A",
      targetTitle: "Intro to Programming",
      citation: DEMO_MAJOR_CITATION(6),
      savings: formatDollars(2043) as string,
    },
  ],
  saveLabel: "YOU SAVE",
} as const;

export const FINAL_CTA = {
  headline: "Know before you apply.",
  body:
    "Pick your route, paste your transcript, and see every verdict - with its receipt - in " +
    "under a minute.",
  cta: "Check my credits →",
  finePrint: `Free · Every California community college · Agreement year ${DEMO_YEAR}`,
} as const;

export const FOOTER = {
  tagline: BADGE,
  links: [{ label: "Citations", href: "#citations" }, ...NAV_LINKS],
  // The landing page's one fine-print ASSIST.org mention (the canonical
  // landing provenance line); exempt from the jargon lint.
  provenance: "Powered by ASSIST.org, California's official transfer database",
} as const;
