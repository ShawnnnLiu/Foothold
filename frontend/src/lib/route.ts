// The app-shell route context (doc 03): the three landing picks, carried as
// the full wire rows so every screen can render names, labels, and ids
// without refetching.

import type { InstitutionRow, MajorRow } from "./api";

export interface RouteContext {
  sending: InstitutionRow;
  receiving: InstitutionRow;
  major: MajorRow;
}
