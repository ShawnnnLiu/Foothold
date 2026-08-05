// The petition drawer's logic (doc F5): the selectable-findings list, the
// default selection, the order-stable positions payload, and letter rendering
// over the poll response. Pure functions of the pre-sorted Evaluation and the
// wire payload; positions into `evaluation.findings` are the stable
// identifiers the backend validates against SELECTABLE_BUCKETS.

import type { Evaluation, EvaluationFindingCode, Finding, PetitionCited } from "./api";

// Drawer timing constants (doc F5): selection changes re-fire the POST after
// this debounce; the poll runs at a fixed interval with a hard attempt cap
// (counted, never wall-clock, so the workflow stays deterministic).
export const POST_DEBOUNCE_MS = 400;
export const POLL_INTERVAL_MS = 1000;
export const POLL_MAX_ATTEMPTS = 30;

export interface PetitionItem {
  // Index into `evaluation.findings`, the wire identifier the POST carries.
  position: number;
  finding: Finding;
}

// Mirrors llm/petition_writer.py SELECTABLE_BUCKETS: only these buckets can
// be petitioned; the backend 422s any other position.
export function petitionItems(evaluation: Evaluation): PetitionItem[] {
  return evaluation.findings
    .map((finding, position) => ({ position, finding }))
    .filter(
      ({ finding }) => finding.bucket === "at_risk" || finding.bucket === "no_articulation",
    );
}

// Doc-F5 defaults: advisement_note, partial_series, and no_articulation
// findings start checked; the other at-risk reasons start unchecked.
const DEFAULT_CHECKED: ReadonlySet<EvaluationFindingCode> = new Set([
  "advisement_note",
  "partial_series",
  "no_articulation",
]);

export function defaultSelection(items: PetitionItem[]): number[] {
  return items
    .filter(({ finding }) => DEFAULT_CHECKED.has(finding.code))
    .map(({ position }) => position);
}

// Toggling keeps the payload ascending, so identical selections always
// serialize identically (the backend's pending-dedup key sorts the same way).
export function toggleSelection(selected: number[], position: number): number[] {
  if (selected.includes(position)) {
    return selected.filter((p) => p !== position);
  }
  return [...selected, position].sort((a, b) => a - b);
}

export function selectionLine(selectedCount: number, itemCount: number): string {
  return `${selectedCount} of ${itemCount} item${itemCount === 1 ? "" : "s"} selected - the letter rebuilds as you check`;
}

// The two underline hold colors the prototype uses: amber for at-risk
// citations, red for no-articulation ones.
export type HoldKind = "amber" | "red";

// course_code -> underline color, from the cited finding's bucket. A position
// outside the findings array cannot happen for a validated response; amber is
// the safe render if it ever did.
export function citedHolds(
  cited: PetitionCited[],
  evaluation: Evaluation,
): Record<string, HoldKind> {
  const holds: Record<string, HoldKind> = {};
  for (const entry of cited) {
    const finding = evaluation.findings[entry.finding_position];
    holds[entry.course_code] = finding?.bucket === "no_articulation" ? "red" : "amber";
  }
  return holds;
}

// Blank-line paragraph split; single newlines stay inside a paragraph (the
// sign-off block) and render with `white-space: pre-line`.
export function letterParagraphs(letterText: string | null): string[] {
  if (letterText === null) {
    return [];
  }
  return letterText
    .split(/\r?\n\s*\r?\n/)
    .map((paragraph) => paragraph.trim())
    .filter((paragraph) => paragraph.length > 0);
}

export interface LetterSegment {
  text: string;
  hold: HoldKind | null;
}

function isCodeChar(ch: string | undefined): boolean {
  return ch !== undefined && /[A-Za-z0-9]/.test(ch);
}

// Exact-string match of validator-confirmed codes only, and only at word
// boundaries: the letter legitimately names other course codes (receiving
// courses, missing series members like "CHEM 2AL"), so a cited "CHEM 2A"
// must not underline itself inside one of them. Longer codes win a shared
// start index so "MATH 1B" never renders as an underlined "MATH 1" plus a
// bare "B".
export function paragraphSegments(
  paragraph: string,
  holds: Record<string, HoldKind>,
): LetterSegment[] {
  const codes = Object.keys(holds).sort((a, b) => b.length - a.length || a.localeCompare(b));
  const segments: LetterSegment[] = [];
  let cursor = 0;
  while (cursor < paragraph.length) {
    let matchIndex = -1;
    let matchCode: string | null = null;
    for (const code of codes) {
      let index = paragraph.indexOf(code, cursor);
      while (
        index !== -1 &&
        (isCodeChar(paragraph[index - 1]) || isCodeChar(paragraph[index + code.length]))
      ) {
        index = paragraph.indexOf(code, index + 1);
      }
      if (index !== -1 && (matchIndex === -1 || index < matchIndex)) {
        matchIndex = index;
        matchCode = code;
      }
    }
    if (matchCode === null) {
      segments.push({ text: paragraph.slice(cursor), hold: null });
      break;
    }
    if (matchIndex > cursor) {
      segments.push({ text: paragraph.slice(cursor, matchIndex), hold: null });
    }
    segments.push({ text: matchCode, hold: holds[matchCode] ?? null });
    cursor = matchIndex + matchCode.length;
  }
  return segments;
}
