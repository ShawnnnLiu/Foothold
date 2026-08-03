import { describe, expect, it } from "vitest";

import type { CourseHit, InstitutionRow, MajorRow } from "./api";
import { assembleDemo, DEMO_PRESETS, type DemoDeps, pickDemoIndex } from "./demo";

function institution(assist_id: number, kind: "cc" | "uc" | "csu" = "cc"): InstitutionRow {
  return { assist_id, code: `I${assist_id}`, name: `Institution ${assist_id}`, kind };
}

function hit(code: string): CourseHit {
  return { course_code: code, title: `Title of ${code}`, units_min: 4, units_max: 4 };
}

describe("DEMO_PRESETS", () => {
  it("holds the sixteen mined routes with unique pairs and colleges", () => {
    expect(DEMO_PRESETS).toHaveLength(16);
    const triples = DEMO_PRESETS.map((p) => `${p.sending_id}/${p.receiving_id}/${p.major_key}`);
    expect(new Set(triples).size).toBe(DEMO_PRESETS.length);
    const colleges = DEMO_PRESETS.map((p) => p.sending_id);
    expect(new Set(colleges).size).toBe(DEMO_PRESETS.length);
  });

  it("keeps every course list demo-sized, deduped, and normalized", () => {
    for (const preset of DEMO_PRESETS) {
      expect(preset.courses.length).toBeGreaterThanOrEqual(9);
      expect(preset.courses.length).toBeLessThanOrEqual(14);
      expect(new Set(preset.courses).size).toBe(preset.courses.length);
      for (const code of preset.courses) {
        expect(code).toBe(code.trim().toUpperCase());
      }
      // no honors twin of a course already on the transcript
      for (const code of preset.courses) {
        expect(preset.courses).not.toContain(`${code}H`);
      }
    }
  });

  it("carries well-formed route identifiers", () => {
    for (const preset of DEMO_PRESETS) {
      expect(preset.sending_id).toBeGreaterThan(0);
      expect(preset.receiving_id).toBeGreaterThan(0);
      expect(preset.major_key).toContain(`/${preset.sending_id}/to/${preset.receiving_id}/Major/`);
      expect(preset.sending_name.length).toBeGreaterThan(0);
      expect(preset.receiving_name.length).toBeGreaterThan(0);
      expect(preset.major_label.length).toBeGreaterThan(0);
    }
  });
});

describe("pickDemoIndex", () => {
  it("maps the random draw onto the preset range", () => {
    expect(pickDemoIndex(16, () => 0)).toBe(0);
    expect(pickDemoIndex(16, () => 0.999)).toBe(15);
    expect(pickDemoIndex(16, () => 0.5)).toBe(8);
  });

  it("never repeats the excluded index when another choice exists", () => {
    expect(pickDemoIndex(16, () => 0, 0)).toBe(1);
    expect(pickDemoIndex(16, () => 0.999, 15)).toBe(0);
    expect(pickDemoIndex(16, () => 0.5, 3)).toBe(8);
  });

  it("returns the only preset even when excluded", () => {
    expect(pickDemoIndex(1, () => 0.7, 0)).toBe(0);
  });
});

describe("assembleDemo", () => {
  const preset = {
    sending_id: 113,
    sending_name: "De Anza College",
    receiving_id: 79,
    receiving_name: "University of California, Berkeley",
    major_key: "76/113/to/79/Major/abc",
    major_label: "EECS B.S.",
    courses: ["MATH 1A", "PHYS 4A"],
  };
  const major: MajorRow = { assist_key: preset.major_key, label: "EECS B.S.", year_label: "2025-2026" };

  function deps(overrides: Partial<DemoDeps> = {}): DemoDeps {
    return {
      ccs: [institution(113, "cc")],
      targets: [institution(79, "uc")],
      fetchMajors: () => Promise.resolve({ majors: [major] }),
      search: (_institutionId, q) => Promise.resolve([hit(q)]),
      ...overrides,
    };
  }

  it("assembles the route from fetched rows and confirms every chip", async () => {
    const start = await assembleDemo(preset, deps());
    expect(start.route.sending.assist_id).toBe(113);
    expect(start.route.receiving.assist_id).toBe(79);
    expect(start.route.major).toEqual(major);
    expect(start.chips.map((chip) => chip.course_code)).toEqual(["MATH 1A", "PHYS 4A"]);
    expect(start.unresolved).toEqual([]);
  });

  it("reports codes the autocomplete cannot confirm instead of dropping them silently", async () => {
    const start = await assembleDemo(
      preset,
      deps({
        search: (_institutionId, q) =>
          Promise.resolve(q === "MATH 1A" ? [hit("MATH 1A")] : []),
      }),
    );
    expect(start.chips.map((chip) => chip.course_code)).toEqual(["MATH 1A"]);
    expect(start.unresolved).toEqual(["PHYS 4A"]);
  });

  it("throws when the preset institutions are missing from the lists", async () => {
    await expect(assembleDemo(preset, deps({ ccs: [] }))).rejects.toThrow(
      "demo route unavailable",
    );
  });

  it("throws when the preset major is no longer published for the pair", async () => {
    await expect(
      assembleDemo(preset, deps({ fetchMajors: () => Promise.resolve({ majors: [] }) })),
    ).rejects.toThrow("demo major unavailable");
  });

  it("throws when nothing resolves", async () => {
    await expect(
      assembleDemo(preset, deps({ search: () => Promise.resolve([]) })),
    ).rejects.toThrow("did not resolve");
  });
});
