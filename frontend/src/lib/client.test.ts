import { describe, expect, it } from "vitest";

import { ApiError, errorText } from "./client";

describe("errorText", () => {
  it("renders an ApiError through its error_body.error text", () => {
    const error = new ApiError(409, {
      error: "evaluation already exists",
      type: "conflict",
      reason_code: null,
    });
    expect(errorText(error)).toBe("evaluation already exists");
  });

  it("renders a plain Error through its message", () => {
    expect(errorText(new TypeError("Failed to fetch"))).toBe("Failed to fetch");
  });

  it("stringifies anything else", () => {
    expect(errorText("boom")).toBe("boom");
  });
});
