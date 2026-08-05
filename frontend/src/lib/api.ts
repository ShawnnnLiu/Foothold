// Wire types, hand-mirrored from backend/schemas/*.json and the doc-01 route
// shapes. Field names stay snake_case, field-for-field with the backend; there
// is no camelCase mapping layer, ever.

// String-literal unions copied from docs/specs/reason_codes.schema.md.
export type TriageBucket = "transfers_clean" | "at_risk" | "no_articulation" | "still_owed";

export type EvaluationFindingCode =
  | "transfers_clean"
  | "advisement_note"
  | "partial_series"
  | "fuzzy_match"
  | "stale_year"
  | "no_articulation"
  | "still_owed"
  | "double_count_risk"
  | "unresolved";

// The ground-truth pointer a finding carries; a partial citation is none.
export interface Citation {
  assist_key: string;
  position: number;
  year_label: string;
}

// Invariants a consumer may rely on (enforced by the backend contract):
// - `citation` is non-null for the seven codes claiming a published
//   articulation (transfers_clean, advisement_note, partial_series,
//   fuzzy_match, stale_year, double_count_risk, still_owed) and null for
//   no_articulation and unresolved.
// - `advisement_note` always carries a non-empty `advisements` list; an
//   advisement the student cannot read is a silently dropped advisement.
// - `bucket` is derived from `code` via the normative BUCKET_FOR_CODE table
//   in docs/specs/reason_codes.schema.md.
export interface Finding {
  code: EvaluationFindingCode;
  bucket: TriageBucket;
  student_course_codes: string[];
  receiving_course_code: string | null;
  receiving_course_title: string | null;
  units: number;
  citation: Citation | null;
  advisements: string[];
  detail: string | null;
}

// One resolved input course; unresolved input becomes an `unresolved`
// finding instead, so this list is exactly what the evaluator reasoned about.
export interface StudentCourse {
  course_code: string;
  title: string | null;
  units: number;
  resolution: "exact" | "fuzzy_match";
}

// The four unit totals deliberately do not sum to the student's total units:
// `still_owed_units` counts requirement units no student course covers.
// Dollar fields are null when the target has no curated cost row; render
// null as absent, never $0.
export interface UnitsSummary {
  clean_units: number;
  at_risk_units: number;
  no_articulation_units: number;
  still_owed_units: number;
  at_risk_dollars: number | null;
  no_articulation_dollars: number | null;
}

// `findings` arrive pre-sorted by the evaluator's `sort_findings` and are
// never re-sorted client-side.
export interface Evaluation {
  evaluation_id: string;
  sending_institution_id: number;
  receiving_institution_id: number;
  major_key: string;
  dept_keys: string[];
  year_id: number;
  year_label: string;
  student_courses: StudentCourse[];
  findings: Finding[];
  units: UnitsSummary;
  created_at: string;
}

// One Mode B row (`GET /api/arbitrage`), mirrored from
// backend/schemas/arbitrage.schema.json. Invariants a consumer may rely on:
// - exactly one of `receiving_course_code` and `receiving_series_name` is
//   non-null, and `receiving_course_title` rides with the code;
// - `citation` is always present: Mode B never emits an uncited row;
// - `savings_dollars` is null when the target publishes no per-unit rate;
//   render null as absent, never $0.
export interface ArbitrageRow {
  missing_course_codes: string[];
  receiving_course_code: string | null;
  receiving_course_title: string | null;
  receiving_series_name: string | null;
  units: number;
  savings_dollars: number | null;
  citation: Citation;
}

// `rows` arrive pre-ranked by the server (savings descending, unrankable
// rows after all dollar rows) and are never re-sorted client-side.
// `omitted_no_rate` counts the rows shown without a savings figure; the
// per-unit rates echo the curated cost table (null when uncurated).
export interface ArbitrageResponse {
  rows: ArbitrageRow[];
  omitted_no_rate: number;
  cc_per_unit: number | null;
  target_per_unit: number | null;
}

// Doc-01 route row shapes.

export interface InstitutionRow {
  assist_id: number;
  code: string;
  name: string;
  kind: "cc" | "uc" | "csu";
}

export interface MajorRow {
  assist_key: string;
  label: string;
  year_label: string;
}

export interface CourseHit {
  course_code: string;
  title: string;
  units_min: number;
  units_max: number;
}

export interface ErrorBody {
  error: string;
  type: string;
  reason_code: string | null;
}

// `POST /api/evaluations` request body; the server never trusts client units
// or titles, so a course entry is the code alone.
export interface EvaluationRequestBody {
  sending_institution_id: number;
  receiving_institution_id: number;
  major_key: string;
  courses: { course_code: string }[];
}

// Doc-F5 locked petition shapes.

export type PetitionStatus = "pending" | "succeeded" | "failed";

// One validator-confirmed citation: this exact course code appears in the
// letter and belongs to the finding at this position.
export interface PetitionCited {
  course_code: string;
  finding_position: number;
}

// `GET /api/petitions/{petition_id}` poll body. Invariants a consumer may
// rely on:
// - `succeeded` with `fallback: true` is the deterministic template letter
//   after repair exhaustion; `reason_code` says why the LLM draft was
//   discarded.
// - `cited` lists every course code the citation validator confirmed in the
//   letter; no other course codes exist in `letter_text`, so exact string
//   matching client-side cannot invent a citation.
export interface PetitionPollResponse {
  status: PetitionStatus;
  reason_code: string | null;
  fallback: boolean;
  letter_text: string | null;
  cited: PetitionCited[];
}

// `POST /api/evaluations/{evaluation_id}/petition` body: indexes into the
// stored evaluation's `findings` array (deterministic order, so positions
// are stable identifiers); each must reference an `at_risk` or
// `no_articulation` finding.
export interface PetitionRequestBody {
  finding_positions: number[];
}
