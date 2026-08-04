import { describe, expect, it } from "vitest";

import {
  BADGE,
  CITATIONS_SECTION,
  FINAL_CTA,
  FOOTER,
  HERO,
  LETTER,
  METHOD_SECTION,
  MOCKUP,
  NAV_LINKS,
  PETITIONS_SECTION,
  PROOF,
  SAVINGS_SECTION,
  STAKES_SECTION,
  STAKES_WALL_STEPS,
} from "./landing";

// Every string the landing page shows outside the two exemptions below.
// LETTER depicts product output addressed to an admissions office, and
// FOOTER.provenance is the landing page's one canonical ASSIST.org
// fine-print line (PLAIN_LANGUAGE.md).
const DISPLAY_SURFACES: unknown[] = [
  NAV_LINKS,
  BADGE,
  HERO,
  MOCKUP,
  PROOF,
  CITATIONS_SECTION,
  METHOD_SECTION,
  PETITIONS_SECTION,
  STAKES_SECTION,
  SAVINGS_SECTION,
  FINAL_CTA,
  FOOTER.tagline,
  FOOTER.links,
];

// Internal identifiers ride along in the content model but are not display
// copy (PLAIN_LANGUAGE.md: a label and its identifier may disagree).
const IDENTIFIER_KEYS = new Set(["bucket", "reasonCode", "kind", "href", "assist_key"]);

function collectStrings(value: unknown, out: string[] = []): string[] {
  if (typeof value === "string") {
    out.push(value);
  } else if (Array.isArray(value)) {
    value.forEach((v) => collectStrings(v, out));
  } else if (value !== null && typeof value === "object") {
    Object.entries(value).forEach(([key, v]) => {
      if (!IDENTIFIER_KEYS.has(key)) {
        collectStrings(v, out);
      }
    });
  }
  return out;
}

describe("canonical strings (PLAIN_LANGUAGE.md)", () => {
  it("pins the landing tagline", () => {
    expect(HERO.tagline).toBe(
      "Foothold checks every course against the official transfer agreement between your " +
        "two schools - and every verdict cites the exact line it came from.",
    );
  });

  it("pins the landing CTA on both foil placements", () => {
    expect(HERO.cta).toBe("Check my credits →");
    expect(FINAL_CTA.cta).toBe("Check my credits →");
  });

  it("pins the landing provenance line", () => {
    expect(FOOTER.provenance).toBe(
      "Powered by ASSIST.org, California's official transfer database",
    );
  });

  it("pins the verdict labels on the mockup rows", () => {
    expect(MOCKUP.rows.map((row) => row.label)).toEqual([
      "TRANSFERS CLEAN",
      "AT RISK",
      "WON'T TRANSFER",
    ]);
  });

  it("pins the board tabs on the mockup title bar", () => {
    expect(MOCKUP.tabs).toEqual(["YOUR CREDITS", "SAVE MONEY"]);
  });

  it("derives the mockup count lines through format.ts", () => {
    expect(MOCKUP.rows[0]?.countLine).toBe("1 COURSE · 5 UNITS");
    expect(MOCKUP.rows[1]?.countLine).toBe("6 COURSES · 24.5 UNITS · ~$2,450 AT STAKE");
    expect(MOCKUP.rows[2]?.countLine).toBe("1 COURSE · 5 UNITS · ~$500");
  });

  it("keeps the method card on the theater's check-line format", () => {
    expect(METHOD_SECTION.steps.map((s) => s.label)).toEqual([
      "Resolved 8 of 8 courses",
      "Ran 14 checks against the official agreement",
      "Flagged 6 fine-print conditions",
      "Verdicts locked - agreement year 2025-2026",
    ]);
  });

  it("captions the wall with the honest count plus the coined suffixes", () => {
    expect(STAKES_SECTION.captionTop).toBe("5 of 34.5 units secure before the check.");
    expect(STAKES_SECTION.captionBottom).toBe(
      "24.5 more within reach - if you fight the flags.",
    );
  });
});

describe("plain-language rules", () => {
  const strings = collectStrings(DISPLAY_SURFACES);

  it("collected the copy it lints", () => {
    expect(strings.length).toBeGreaterThan(40);
  });

  it("shows no transfer-office jargon in display copy", () => {
    for (const s of strings) {
      expect(s).not.toMatch(/triage/i);
      expect(s).not.toMatch(/arbitrage/i);
      expect(s).not.toMatch(/articulat/i);
      // The locked doc-02 reason tags render through ReasonTag, not these
      // strings, so "advisement" never appears here either.
      expect(s).not.toMatch(/advisement/i);
    }
  });

  it("names ASSIST only in the one fine-print provenance line", () => {
    for (const s of strings) {
      expect(s).not.toMatch(/assist/i);
    }
    expect(FOOTER.provenance).toContain("ASSIST.org");
  });

  it("uses no em dashes anywhere, including the letter", () => {
    for (const s of collectStrings([DISPLAY_SURFACES, LETTER, FOOTER.provenance])) {
      expect(s).not.toContain("—");
    }
  });
});

describe("the stakes wall", () => {
  it("is the export's six fixed steps, secure at the base, still-needed on top", () => {
    expect(STAKES_WALL_STEPS.map((s) => s.kind)).toEqual([
      "secure",
      "reach",
      "reach",
      "reach",
      "reach",
      "owed",
    ]);
  });
});
