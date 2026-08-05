import { describe, expect, it } from "vitest";

import type { Evaluation, PetitionPollResponse } from "./api";
import evaluationFixture from "./__fixtures__/evaluation.demo.json";
import petitionFixture from "./__fixtures__/petition.demo.json";
import {
  citedHolds,
  defaultSelection,
  letterParagraphs,
  paragraphSegments,
  petitionItems,
  selectionLine,
  toggleSelection,
} from "./petition";

const demoEvaluation = evaluationFixture as unknown as Evaluation;
const demoPoll = petitionFixture as PetitionPollResponse;

describe("petitionItems", () => {
  it("lists exactly the at-risk and no-articulation findings with their positions", () => {
    const items = petitionItems(demoEvaluation);
    expect(items.map(({ position }) => position)).toStrictEqual([14, 15, 16, 17, 18]);
    for (const { position, finding } of items) {
      expect(finding).toBe(demoEvaluation.findings[position]);
      expect(["at_risk", "no_articulation"]).toContain(finding.bucket);
    }
  });

  it("is empty for an all-clean evaluation (the sidebar button stays disabled)", () => {
    const clean = structuredClone(demoEvaluation);
    clean.findings = clean.findings.filter(
      (finding) => finding.bucket !== "at_risk" && finding.bucket !== "no_articulation",
    );
    expect(petitionItems(clean)).toStrictEqual([]);
  });
});

describe("defaultSelection", () => {
  it("checks advisement_note, partial_series, and no_articulation findings", () => {
    expect(defaultSelection(petitionItems(demoEvaluation))).toStrictEqual([14, 15, 16, 17, 18]);
  });

  it("leaves the other at-risk reasons unchecked", () => {
    const altered = structuredClone(demoEvaluation);
    const template = altered.findings[14]!;
    altered.findings.push(
      { ...template, code: "fuzzy_match" },
      { ...template, code: "stale_year" },
      { ...template, code: "double_count_risk" },
      { ...template, code: "unresolved", citation: null },
    );
    expect(defaultSelection(petitionItems(altered))).toStrictEqual([14, 15, 16, 17, 18]);
  });
});

describe("toggleSelection", () => {
  it("removes a selected position and keeps the rest", () => {
    expect(toggleSelection([14, 16, 18], 16)).toStrictEqual([14, 18]);
  });

  it("adds an unselected position in ascending order (the payload is order-stable)", () => {
    expect(toggleSelection([14, 18], 16)).toStrictEqual([14, 16, 18]);
    expect(toggleSelection([], 18)).toStrictEqual([18]);
  });

  it("does not mutate its input", () => {
    const selected = [14, 18];
    toggleSelection(selected, 16);
    expect(selected).toStrictEqual([14, 18]);
  });
});

describe("selectionLine", () => {
  it("counts selected of total, singular at one", () => {
    expect(selectionLine(3, 5)).toBe("3 of 5 items selected - the letter rebuilds as you check");
    expect(selectionLine(1, 1)).toBe("1 of 1 item selected - the letter rebuilds as you check");
  });
});

describe("citedHolds", () => {
  it("colors at-risk citations amber and no-articulation citations red", () => {
    expect(citedHolds(demoPoll.cited, demoEvaluation)).toStrictEqual({
      "MATH 1C": "amber",
      "CIS 22B": "red",
    });
  });
});

describe("letterParagraphs", () => {
  it("splits the fixture letter on blank lines, keeping single newlines inside a paragraph", () => {
    const paragraphs = letterParagraphs(demoPoll.letter_text);
    expect(paragraphs).toHaveLength(4);
    expect(paragraphs[0]).toBe("To the Office of Admissions, UC San Diego:");
    expect(paragraphs[3]).toContain("Sincerely,\n[Your name]");
  });

  it("handles CRLF blank lines and returns [] for a null letter (the failed shape)", () => {
    expect(letterParagraphs("first\r\n\r\nsecond")).toStrictEqual(["first", "second"]);
    const failed: PetitionPollResponse = {
      status: "failed",
      reason_code: "auth_failed",
      fallback: false,
      letter_text: null,
      cited: [],
    };
    expect(letterParagraphs(failed.letter_text)).toStrictEqual([]);
  });

  it("renders the fallback template letter through the same split", () => {
    const fallback: PetitionPollResponse = {
      ...demoPoll,
      fallback: true,
      reason_code: "repair_limit_exceeded",
    };
    expect(letterParagraphs(fallback.letter_text)).toHaveLength(4);
  });
});

describe("paragraphSegments", () => {
  const holds = citedHolds(demoPoll.cited, demoEvaluation);

  it("underlines only validator-confirmed codes, in their finding's hold color", () => {
    const paragraphs = letterParagraphs(demoPoll.letter_text);
    const petitionParagraph = paragraphs[1]!;
    const segments = paragraphSegments(petitionParagraph, holds);
    expect(segments.filter(({ hold }) => hold !== null)).toStrictEqual([
      { text: "MATH 1C", hold: "amber" },
    ]);
    // Uncited course codes in the same paragraph stay plain text.
    expect(segments.map(({ text }) => text).join("")).toBe(petitionParagraph);
    const reviewSegments = paragraphSegments(paragraphs[2]!, holds);
    expect(reviewSegments.filter(({ hold }) => hold !== null)).toStrictEqual([
      { text: "CIS 22B", hold: "red" },
    ]);
  });

  it("returns one plain segment when nothing is cited", () => {
    expect(paragraphSegments("Thank you for your review.", holds)).toStrictEqual([
      { text: "Thank you for your review.", hold: null },
    ]);
    expect(paragraphSegments("Thank you.", {})).toStrictEqual([
      { text: "Thank you.", hold: null },
    ]);
  });

  it("does not underline a cited code embedded in a longer course code", () => {
    // Seen live: the letter said "with CHEM 2AL noted as missing" and the
    // cited "CHEM 2A" underlined itself inside "CHEM 2AL".
    expect(
      paragraphSegments("with CHEM 2AL noted as missing", { "CHEM 2A": "amber" }),
    ).toStrictEqual([{ text: "with CHEM 2AL noted as missing", hold: null }]);
    expect(paragraphSegments("BCHEM 2A is not CHEM 2A", { "CHEM 2A": "amber" })).toStrictEqual([
      { text: "BCHEM 2A is not ", hold: null },
      { text: "CHEM 2A", hold: "amber" },
    ]);
  });

  it("prefers the longest code at a shared start index", () => {
    const overlapping = { "MATH 1": "amber", "MATH 1C": "red" } as const;
    expect(paragraphSegments("take MATH 1C now", overlapping)).toStrictEqual([
      { text: "take ", hold: null },
      { text: "MATH 1C", hold: "red" },
      { text: " now", hold: null },
    ]);
  });
});
