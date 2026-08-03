import { describe, expect, it } from "vitest";

import type { CourseHit } from "./api";
import {
  addChip,
  clearInput,
  EMPTY_CHIP_STATE,
  extractCourseCodes,
  loadSample,
  popChip,
  removeChip,
  SAMPLE_COURSES,
  setInput,
  suggestions,
} from "./courses";

function hit(code: string): CourseHit {
  return { course_code: code, title: `Title of ${code}`, units_min: 5, units_max: 5 };
}

describe("chip transitions", () => {
  it("addChip appends in insertion order and clears the input", () => {
    const one = addChip(setInput(EMPTY_CHIP_STATE, "ma"), hit("MATH 1A"));
    expect(one).toStrictEqual({ chips: [hit("MATH 1A")], input: "" });
    const two = addChip(setInput(one, "ci"), hit("CIS 22B"));
    expect(two.chips.map((chip) => chip.course_code)).toStrictEqual(["MATH 1A", "CIS 22B"]);
    expect(two.input).toBe("");
  });

  it("addChip of a duplicate course_code is a no-op that still clears the input", () => {
    const one = addChip(EMPTY_CHIP_STATE, hit("MATH 1A"));
    const again = addChip(setInput(one, "math 1a"), hit("MATH 1A"));
    expect(again.chips).toStrictEqual(one.chips);
    expect(again.input).toBe("");
  });

  it("removeChip removes exactly the named code", () => {
    const state = addChip(addChip(EMPTY_CHIP_STATE, hit("MATH 1A")), hit("CIS 22B"));
    const removed = removeChip(state, "MATH 1A");
    expect(removed.chips.map((chip) => chip.course_code)).toStrictEqual(["CIS 22B"]);
  });

  it("popChip pops the last chip only when the input is empty", () => {
    const state = addChip(addChip(EMPTY_CHIP_STATE, hit("MATH 1A")), hit("CIS 22B"));
    expect(popChip(state).chips.map((chip) => chip.course_code)).toStrictEqual(["MATH 1A"]);
    const typing = setInput(state, "m");
    expect(popChip(typing)).toStrictEqual(typing);
    expect(popChip(EMPTY_CHIP_STATE)).toStrictEqual(EMPTY_CHIP_STATE);
  });

  it("setInput and clearInput touch only the input", () => {
    const state = addChip(EMPTY_CHIP_STATE, hit("MATH 1A"));
    const typed = setInput(state, "cis");
    expect(typed).toStrictEqual({ chips: state.chips, input: "cis" });
    expect(clearInput(typed)).toStrictEqual({ chips: state.chips, input: "" });
  });

  it("loadSample replaces the chips, dedupes by course_code, and clears input", () => {
    const state = loadSample([hit("MATH 1A"), hit("CIS 22B"), hit("MATH 1A")]);
    expect(state.chips.map((chip) => chip.course_code)).toStrictEqual(["MATH 1A", "CIS 22B"]);
    expect(state.input).toBe("");
  });

  it("transitions never mutate their input state", () => {
    const state = addChip(addChip(EMPTY_CHIP_STATE, hit("MATH 1A")), hit("CIS 22B"));
    const before = structuredClone(state);
    addChip(state, hit("MATH 22"));
    removeChip(state, "MATH 1A");
    popChip(state);
    setInput(state, "x");
    clearInput(state);
    expect(state).toStrictEqual(before);
  });
});

describe("extractCourseCodes", () => {
  const pasted = `De Anza College - Unofficial Transcript
Student ID 00812345
Fall 2024
MATH 1A  Calculus I  5.0  A
MATH 1B  Calculus II  5.0  A-
CIS 22B  Intermediate Programming Methodologies in C++  4.5  B+
Winter 2025
MATH 1C  Calculus III  5.0  B
MATH 2A  Differential Equations  5.0  A
CIS 22C  Data Abstraction and Structures  4.5  A
Spring 2025
MATH 2B  Linear Algebra  5.0  A
MATH 22  Discrete Mathematics  5.0  B+
CIS 36B  Intermediate Problem Solving in Java  4.5  A
Repeated: MATH 1A honors section
Total units earned: 43.5  GPA 3.72
`;

  it("pins the nine demo codes in first-occurrence order, deduped, plus the GPA noise candidate", () => {
    // "GPA 3" matching is by design: paste extraction only proposes
    // candidates, and each one must be confirmed against the autocomplete
    // API before it can become a chip.
    expect(extractCourseCodes(pasted)).toStrictEqual([
      "MATH 1A",
      "MATH 1B",
      "CIS 22B",
      "MATH 1C",
      "MATH 2A",
      "CIS 22C",
      "MATH 2B",
      "MATH 22",
      "CIS 36B",
      "GPA 3",
    ]);
  });

  it("uppercases lowercase input before matching", () => {
    expect(extractCourseCodes("i took math 1a and cis 22b last fall")).toStrictEqual([
      "MATH 1A",
      "CIS 22B",
    ]);
  });

  it("returns an empty array when nothing matches", () => {
    expect(extractCourseCodes("no codes here")).toStrictEqual([]);
  });
});

describe("SAMPLE_COURSES", () => {
  it("pins the nine demo-student codes from deanza_ucsd_cs.json", () => {
    expect(SAMPLE_COURSES).toStrictEqual([
      "MATH 1A",
      "MATH 1B",
      "MATH 1C",
      "MATH 2A",
      "MATH 2B",
      "MATH 22",
      "CIS 22B",
      "CIS 22C",
      "CIS 36B",
    ]);
  });
});

describe("suggestions", () => {
  const hit = (code: string): CourseHit => ({
    course_code: code,
    title: code,
    units_min: 4,
    units_max: 4,
  });

  it("preserves server order, hides codes already chipped, caps at 8", () => {
    const hits = Array.from({ length: 10 }, (_, i) => hit(`MATH ${i}`));
    const state = addChip(EMPTY_CHIP_STATE, hit("MATH 3"));
    const shown = suggestions(hits, state);
    expect(shown.map((s) => s.course_code)).toStrictEqual([
      "MATH 0",
      "MATH 1",
      "MATH 2",
      "MATH 4",
      "MATH 5",
      "MATH 6",
      "MATH 7",
      "MATH 8",
    ]);
  });

  it("returns all hits unchanged when nothing is chipped and under the cap", () => {
    const hits = [hit("CIS 22A"), hit("CIS 22B")];
    expect(suggestions(hits, EMPTY_CHIP_STATE)).toStrictEqual(hits);
  });
});
