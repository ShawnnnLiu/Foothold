// Chip-state transitions for the course-entry screen: pure functions over
// ChipState, insertion order preserved, never sorted. Dedupe key is
// `course_code`; a duplicate add is a no-op that still clears the input.

import type { CourseHit } from "./api";

export interface ChipState {
  chips: CourseHit[];
  input: string;
}

export const EMPTY_CHIP_STATE: ChipState = { chips: [], input: "" };

export function addChip(state: ChipState, hit: CourseHit): ChipState {
  const duplicate = state.chips.some((chip) => chip.course_code === hit.course_code);
  return {
    chips: duplicate ? state.chips : [...state.chips, hit],
    input: "",
  };
}

export function removeChip(state: ChipState, code: string): ChipState {
  return {
    chips: state.chips.filter((chip) => chip.course_code !== code),
    input: state.input,
  };
}

// Backspace-on-empty-input: pops the last chip; with pending input the state
// is unchanged (the backspace edits the input itself).
export function popChip(state: ChipState): ChipState {
  if (state.input !== "" || state.chips.length === 0) {
    return state;
  }
  return { chips: state.chips.slice(0, -1), input: state.input };
}

export function setInput(state: ChipState, input: string): ChipState {
  return { chips: state.chips, input };
}

export function clearInput(state: ChipState): ChipState {
  return { chips: state.chips, input: "" };
}

// Replaces the chip set wholesale (the demo-student sample), deduped by
// course_code preserving first occurrence, input cleared.
export function loadSample(sample: CourseHit[]): ChipState {
  const seen = new Set<string>();
  const chips: CourseHit[] = [];
  for (const hit of sample) {
    if (!seen.has(hit.course_code)) {
      seen.add(hit.course_code);
      chips.push(hit);
    }
  }
  return { chips, input: "" };
}

// The nine demo-student codes (data/curated/demo_students/deanza_ucsd_cs.json),
// pinned per doc 03; each is still resolved through the autocomplete API
// before becoming a chip, so a sample chip is never fabricated client-side.
export const SAMPLE_COURSES: readonly string[] = [
  "MATH 1A",
  "MATH 1B",
  "MATH 1C",
  "MATH 2A",
  "MATH 2B",
  "MATH 22",
  "CIS 22B",
  "CIS 22C",
  "CIS 36B",
];

// Suggestion-dropdown projection: server order preserved, chips already added
// are hidden, capped at the doc-03 maximum of 8.
export const MAX_SUGGESTIONS = 8;

export function suggestions(hits: CourseHit[], state: ChipState): CourseHit[] {
  const taken = new Set(state.chips.map((chip) => chip.course_code));
  return hits.filter((hit) => !taken.has(hit.course_code)).slice(0, MAX_SUGGESTIONS);
}

// The locked course-code pattern for the deterministic paste path; every
// candidate is then confirmed against the autocomplete API before it can
// become a chip (nothing enters chips unconfirmed).
const COURSE_CODE_PATTERN = /\b[A-Z]{2,5} ?\d{1,3}[A-Z]{0,2}\b/g;

export function extractCourseCodes(pasted: string): string[] {
  const matches = pasted.toUpperCase().match(COURSE_CODE_PATTERN) ?? [];
  const seen = new Set<string>();
  const codes: string[] = [];
  for (const match of matches) {
    const code = match.replace(/\s+/g, " ");
    if (!seen.has(code)) {
      seen.add(code);
      codes.push(code);
    }
  }
  return codes;
}
