// The triage board view-model: a line-for-line mirror of
// backend/src/starmap/transfer/triage.py `build_triage_board`, plus the
// wall-step elevation model. Pure functions of the pre-sorted Evaluation; no
// re-sorting, no rounding beyond what the backend already did, no PRNG.
// The parity fixture test (evaluation.test.ts) pins this mirror against the
// backend's own output byte-for-byte.

import type { Evaluation, Finding, TriageBucket } from "./api";

// The three credit columns, in the evaluator's locked bucket-rank order;
// still_owed is its own field because those findings describe requirements
// no student course was applied to, not the student's credits.
export type CreditBucket = "transfers_clean" | "at_risk" | "no_articulation";

export const CREDIT_BUCKETS: readonly CreditBucket[] = [
  "transfers_clean",
  "at_risk",
  "no_articulation",
];

// Mirrors transfer/triage.py TriageHeader field-for-field.
export interface TriageHeader {
  clean_units: number;
  at_risk_units: number;
  no_articulation_units: number;
  still_owed_units: number;
  at_risk_dollars: number | null;
  no_articulation_dollars: number | null;
  course_count: number;
  finding_count: number;
}

export interface TriageBoard {
  columns: Record<CreditBucket, Finding[]>;
  still_owed: Finding[];
  header: TriageHeader;
}

export function buildTriageBoard(evaluation: Evaluation): TriageBoard {
  const byBucket: Record<TriageBucket, Finding[]> = {
    transfers_clean: [],
    at_risk: [],
    no_articulation: [],
    still_owed: [],
  };
  for (const finding of evaluation.findings) {
    byBucket[finding.bucket].push(finding);
  }
  return {
    columns: {
      transfers_clean: byBucket.transfers_clean,
      at_risk: byBucket.at_risk,
      no_articulation: byBucket.no_articulation,
    },
    still_owed: byBucket.still_owed,
    header: {
      clean_units: evaluation.units.clean_units,
      at_risk_units: evaluation.units.at_risk_units,
      no_articulation_units: evaluation.units.no_articulation_units,
      still_owed_units: evaluation.units.still_owed_units,
      at_risk_dollars: evaluation.units.at_risk_dollars,
      no_articulation_dollars: evaluation.units.no_articulation_dollars,
      course_count: evaluation.student_courses.length,
      finding_count: evaluation.findings.length,
    },
  };
}

// The four evaluation-theater check lines, filled ONLY from the real response
// (doc 03): resolved counts the courses the evaluator reasoned about, total
// adds the unresolved findings, so the two always sum to what was submitted.
export function theaterLines(evaluation: Evaluation): [string, string, string, string] {
  const resolved = evaluation.student_courses.length;
  const unresolvedCount = evaluation.findings.filter((f) => f.code === "unresolved").length;
  const advisementCount = evaluation.findings.filter((f) => f.advisements.length > 0).length;
  return [
    `Resolved ${resolved} of ${resolved + unresolvedCount} courses`,
    `Evaluated ${evaluation.findings.length} articulation findings`,
    `Checked ${advisementCount} advisements`,
    `Verdicts locked - agreement year ${evaluation.year_label}`,
  ];
}

// course_code -> title for rendering a finding's sending-side titles; the
// student_courses list is exactly what the evaluator resolved.
export function studentTitleMap(evaluation: Evaluation): Record<string, string | null> {
  const titles: Record<string, string | null> = {};
  for (const course of evaluation.student_courses) {
    titles[course.course_code] = course.title;
  }
  return titles;
}

export interface WallStep {
  kind: "secure" | "reach" | "owed";
}

// The elevation chart's fixed step count (the prototype's count).
export const WALL_STEP_COUNT = 7;

// Decorative-proportional only: the honest numbers live in the caption
// (format.ts wallCaption). A zero total returns an empty array and the chart
// is omitted, never fabricated (ASCENT.md elevation chart rule).
export function wallSteps(header: TriageHeader): WallStep[] {
  const clean = header.clean_units;
  const atRisk = header.at_risk_units;
  const owedUnits = header.still_owed_units;
  const total = clean + atRisk + owedUnits;
  if (total === 0) {
    return [];
  }
  let secure = clean > 0 ? Math.max(1, Math.round((WALL_STEP_COUNT * clean) / total)) : 0;
  let owed = owedUnits > 0 ? Math.max(1, Math.round((WALL_STEP_COUNT * owedUnits) / total)) : 0;
  let reach = Math.max(0, WALL_STEP_COUNT - secure - owed);
  if (reach === 0 && atRisk > 0) {
    // Steal one step from the larger of secure/owed so at-risk stays visible.
    if (secure >= owed) {
      secure -= 1;
    } else {
      owed -= 1;
    }
    reach = 1;
  }
  return [
    ...Array.from({ length: secure }, (): WallStep => ({ kind: "secure" })),
    ...Array.from({ length: reach }, (): WallStep => ({ kind: "reach" })),
    ...Array.from({ length: owed }, (): WallStep => ({ kind: "owed" })),
  ];
}
