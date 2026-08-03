// Deterministic code-to-chip confirmation for the sample button and the paste
// path: every candidate code is confirmed via the autocomplete API (exact
// `course_code` match among the hits) before it can become a chip; unconfirmed
// codes are reported, never silently dropped. The search function is injected
// so this stays a pure orchestration over its results.

import type { CourseHit } from "./api";

export interface ResolveResult {
  resolved: CourseHit[];
  unresolved: string[];
}

// The paste/sample status line: what was added, and every unconfirmed code by
// name (no silent drops).
export function parseMessage(result: ResolveResult): string {
  const parts: string[] = [];
  if (result.resolved.length > 0) {
    parts.push(`Added ${result.resolved.length} course${result.resolved.length === 1 ? "" : "s"}`);
  }
  if (result.unresolved.length > 0) {
    parts.push(`${result.unresolved.length} not recognized: ${result.unresolved.join(", ")}`);
  }
  return parts.length > 0 ? parts.join(" · ") : "No course codes found";
}

export async function resolveCodes(
  codes: string[],
  search: (q: string) => Promise<CourseHit[]>,
): Promise<ResolveResult> {
  const hitLists = await Promise.all(codes.map((code) => search(code)));
  const resolved: CourseHit[] = [];
  const unresolved: string[] = [];
  codes.forEach((code, i) => {
    const exact = (hitLists[i] ?? []).find((hit) => hit.course_code === code);
    if (exact) {
      resolved.push(exact);
    } else {
      unresolved.push(code);
    }
  });
  return { resolved, unresolved };
}
