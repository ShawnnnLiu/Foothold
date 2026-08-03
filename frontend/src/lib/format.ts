// Units, dollar, caption, and citation-label formatting. Deterministic string
// building only; every figure flows in from the caller or the view-model,
// never from a literal here.

import type { Citation, EvaluationFindingCode } from "./api";
import type { TriageHeader } from "./evaluation";

// Trailing-zero-free like Python's `:g`: 5 -> "5", 4.5 -> "4.5".
export function formatUnits(n: number): string {
  return String(n);
}

// "~$1,455" style; null means no curated cost row, and callers omit the
// element entirely (never render $0 for unknown).
export function formatDollars(n: number | null): string | null {
  if (n === null) {
    return null;
  }
  return `~$${Math.round(n).toLocaleString("en-US")}`;
}

// The elevation chart's two caption lines, always with the exact figures
// (the chart itself is decorative-proportional; this is the honest count).
export function wallCaption(header: TriageHeader): [string, string] {
  const total = header.clean_units + header.at_risk_units + header.still_owed_units;
  return [
    `${formatUnits(header.clean_units)} of ${formatUnits(total)} units secure`,
    `${formatUnits(header.at_risk_units)} more within reach`,
  ];
}

// The `majorKey` parameter is part of the locked doc-02 signature (reserved
// for future grouping); the branch itself is on the citation's own key.
export function citationLabel(citation: Citation, _majorKey: string): string {
  const kind = citation.assist_key.includes("/Major/") ? "MAJOR AGREEMENT" : "DEPT. AGREEMENT";
  return `${kind} ${citation.year_label} - ARTICULATION #${citation.position}`;
}

// The six locked reason tags; codes outside this map (transfers_clean,
// no_articulation, still_owed) render through their bucket's hold-tile, not
// a reason tag.
export const REASON_TAGS: Partial<Record<EvaluationFindingCode, string>> = {
  advisement_note: "ADVISEMENT NOTE",
  partial_series: "PARTIAL SERIES",
  fuzzy_match: "FUZZY MATCH",
  stale_year: "STALE YEAR",
  double_count_risk: "DOUBLE-COUNT RISK",
  unresolved: "UNRESOLVED",
};
