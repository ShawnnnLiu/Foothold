import { describe, expect, it } from "vitest";

import type { Evaluation } from "./api";
import boardFixture from "./__fixtures__/board.demo.json";
import evaluationFixture from "./__fixtures__/evaluation.demo.json";
import {
  buildTriageBoard,
  distinctCourseCount,
  studentTitleMap,
  theaterLines,
  wallSteps,
} from "./evaluation";
import type { TriageHeader } from "./evaluation";

const demoEvaluation = evaluationFixture as unknown as Evaluation;

describe("buildTriageBoard", () => {
  it("matches the backend-dumped board fixture (the cross-language parity pin)", () => {
    expect(buildTriageBoard(demoEvaluation)).toStrictEqual(boardFixture);
  });

  it("is pure: same input gives deep-equal output and the input is not mutated", () => {
    const before = structuredClone(demoEvaluation);
    const first = buildTriageBoard(demoEvaluation);
    const second = buildTriageBoard(demoEvaluation);
    expect(first).toStrictEqual(second);
    expect(demoEvaluation).toStrictEqual(before);
  });

  it("preserves the findings' incoming order in every column (no re-sorting)", () => {
    const board = buildTriageBoard(demoEvaluation);
    for (const bucket of ["transfers_clean", "at_risk", "no_articulation"] as const) {
      expect(board.columns[bucket]).toStrictEqual(
        demoEvaluation.findings.filter((finding) => finding.bucket === bucket),
      );
    }
    expect(board.still_owed).toStrictEqual(
      demoEvaluation.findings.filter((finding) => finding.bucket === "still_owed"),
    );
  });
});

describe("distinctCourseCount", () => {
  it("counts a course once across its per-line and double-count findings", () => {
    const first = demoEvaluation.findings.find((finding) => finding.bucket === "at_risk")
      ?? demoEvaluation.findings[0]!;
    const findings = [
      { ...first, student_course_codes: ["KNES 11"] },
      { ...first, student_course_codes: ["KNES 11"] },
      { ...first, code: "double_count_risk" as const, student_course_codes: ["KNES 11"] },
      { ...first, student_course_codes: ["KNES 20"] },
    ];
    expect(distinctCourseCount(findings)).toBe(2);
  });

  it("counts every code of a multi-course finding and none for an empty column", () => {
    const first = demoEvaluation.findings[0]!;
    expect(distinctCourseCount([{ ...first, student_course_codes: ["PHYS 4A", "PHYS 4B"] }])).toBe(
      2,
    );
    expect(distinctCourseCount([])).toBe(0);
  });
});

describe("theaterLines", () => {
  it("pins the demo evaluation's four lines (numbers from the response, never placeholders)", () => {
    expect(theaterLines(demoEvaluation)).toStrictEqual([
      "Resolved 9 of 9 courses",
      "Ran 21 checks against the official agreement",
      "Flagged 0 fine-print conditions",
      "Verdicts locked - agreement year 2025-2026",
    ]);
  });

  it("counts unresolved findings into the course total and advisement-bearing findings into line 3", () => {
    const altered = structuredClone(demoEvaluation);
    const first = altered.findings[0]!;
    altered.findings.push({
      ...first,
      code: "unresolved",
      bucket: "at_risk",
      citation: null,
      student_course_codes: ["PHYS 4A"],
    });
    first.advisements = ["Must complete entire series"];
    expect(theaterLines(altered)[0]).toBe("Resolved 9 of 10 courses");
    expect(theaterLines(altered)[2]).toBe("Flagged 1 fine-print condition");
  });
});

describe("studentTitleMap", () => {
  it("maps every resolved course code to its title", () => {
    const titles = studentTitleMap(demoEvaluation);
    expect(titles["MATH 1A"]).toBe("Calculus I");
    expect(Object.keys(titles)).toHaveLength(demoEvaluation.student_courses.length);
  });
});

describe("wallSteps", () => {
  it("pins the demo header: clean 34, at risk 5, owed 10 -> secure 5, reach 1, owed 1", () => {
    const board = buildTriageBoard(demoEvaluation);
    expect(wallSteps(board.header)).toStrictEqual([
      { kind: "secure" },
      { kind: "secure" },
      { kind: "secure" },
      { kind: "secure" },
      { kind: "secure" },
      { kind: "reach" },
      { kind: "owed" },
    ]);
  });

  it("returns an empty array for a zero total (chart omitted, never fabricated)", () => {
    const header: TriageHeader = {
      clean_units: 0,
      at_risk_units: 0,
      no_articulation_units: 0,
      still_owed_units: 0,
      at_risk_dollars: null,
      no_articulation_dollars: null,
      course_count: 0,
      finding_count: 0,
    };
    expect(wallSteps(header)).toStrictEqual([]);
  });
});
