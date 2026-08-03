import { describe, expect, it } from "vitest";

import type { Evaluation } from "./api";
import boardFixture from "./__fixtures__/board.demo.json";
import evaluationFixture from "./__fixtures__/evaluation.demo.json";
import { buildTriageBoard, wallSteps } from "./evaluation";
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
