import { describe, expect, it } from "vitest";

import type { Evaluation } from "./api";
import evaluationFixture from "./__fixtures__/evaluation.demo.json";
import { buildTriageBoard } from "./evaluation";
import { citationLabel, formatDollars, formatUnits, REASON_TAGS, wallCaption } from "./format";

const demoEvaluation = evaluationFixture as unknown as Evaluation;
const MAJOR_KEY = "76/113/to/7/Major/d2dfb7a8-d505-4e70-f33c-08ddd3b241a4";

describe("formatUnits", () => {
  it("is trailing-zero-free like Python :g", () => {
    expect(formatUnits(5)).toBe("5");
    expect(formatUnits(4.5)).toBe("4.5");
    expect(formatUnits(34.0)).toBe("34");
  });
});

describe("formatDollars", () => {
  it("renders the ~$1,455 style", () => {
    expect(formatDollars(1455)).toBe("~$1,455");
    expect(formatDollars(1309.5)).toBe("~$1,310");
  });

  it("passes null through so callers omit the element (never $0)", () => {
    expect(formatDollars(null)).toBeNull();
  });
});

describe("wallCaption", () => {
  it("carries the exact demo figures alongside the decorative chart", () => {
    const board = buildTriageBoard(demoEvaluation);
    expect(wallCaption(board.header)).toStrictEqual([
      "34 of 49 units secure",
      "5 more within reach",
    ]);
  });
});

describe("citationLabel", () => {
  it("labels a major-agreement citation", () => {
    expect(
      citationLabel({ assist_key: MAJOR_KEY, position: 2, year_label: "2025-2026" }, MAJOR_KEY),
    ).toBe("MAJOR AGREEMENT 2025-2026 - ARTICULATION #2");
  });

  it("labels a department-agreement citation", () => {
    expect(
      citationLabel(
        { assist_key: "76/113/to/7/Department/3276", position: 0, year_label: "2025-2026" },
        MAJOR_KEY,
      ),
    ).toBe("DEPT. AGREEMENT 2025-2026 - ARTICULATION #0");
  });
});

describe("REASON_TAGS", () => {
  it("maps exactly the six locked at-risk reason tags", () => {
    expect(REASON_TAGS).toStrictEqual({
      advisement_note: "ADVISEMENT NOTE",
      partial_series: "PARTIAL SERIES",
      fuzzy_match: "FUZZY MATCH",
      stale_year: "STALE YEAR",
      double_count_risk: "DOUBLE-COUNT RISK",
      unresolved: "UNRESOLVED",
    });
  });
});
