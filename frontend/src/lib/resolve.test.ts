import { describe, expect, it } from "vitest";

import type { CourseHit } from "./api";
import { parseMessage, resolveCodes } from "./resolve";

function hit(code: string): CourseHit {
  return { course_code: code, title: `Title of ${code}`, units_min: 4, units_max: 4 };
}

const catalog: Record<string, CourseHit[]> = {
  "MATH 1A": [hit("MATH 1A"), hit("MATH 1AH")],
  "CIS 22C": [hit("CIS 22CH"), hit("CIS 22C")],
  "PHYS 4A": [hit("PHYS 4AH")],
};

const search = (q: string) => Promise.resolve(catalog[q] ?? []);

describe("resolveCodes", () => {
  it("confirms only exact course_code matches, preserving input order", async () => {
    const result = await resolveCodes(["MATH 1A", "CIS 22C"], search);
    expect(result.resolved.map((c) => c.course_code)).toStrictEqual(["MATH 1A", "CIS 22C"]);
    expect(result.unresolved).toStrictEqual([]);
  });

  it("reports unconfirmed codes instead of dropping them (near-miss hits do not count)", async () => {
    const result = await resolveCodes(["PHYS 4A", "FAKE 999"], search);
    expect(result.resolved).toStrictEqual([]);
    expect(result.unresolved).toStrictEqual(["PHYS 4A", "FAKE 999"]);
  });

  it("keeps resolved and unresolved interleaved input in stable order", async () => {
    const result = await resolveCodes(["FAKE 1", "MATH 1A", "PHYS 4A", "CIS 22C"], search);
    expect(result.resolved.map((c) => c.course_code)).toStrictEqual(["MATH 1A", "CIS 22C"]);
    expect(result.unresolved).toStrictEqual(["FAKE 1", "PHYS 4A"]);
  });
});

describe("parseMessage", () => {
  it("names every unconfirmed code (no silent drops)", () => {
    expect(parseMessage({ resolved: [hit("MATH 1A")], unresolved: ["PHYS 4A", "FAKE 9"] })).toBe(
      "Added 1 course · 2 not recognized: PHYS 4A, FAKE 9",
    );
  });

  it("reports a clean add plurally", () => {
    expect(parseMessage({ resolved: [hit("MATH 1A"), hit("CIS 22C")], unresolved: [] })).toBe(
      "Added 2 courses",
    );
  });

  it("reports an empty extraction", () => {
    expect(parseMessage({ resolved: [], unresolved: [] })).toBe("No course codes found");
  });
});
