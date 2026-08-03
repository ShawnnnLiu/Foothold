// Typed fetch wrappers over the doc-01 API surface; no logic lives here.
// The `sid` cookie rides along automatically (same-origin requests).

import type {
  CourseHit,
  ErrorBody,
  Evaluation,
  EvaluationRequestBody,
  InstitutionRow,
  MajorRow,
} from "./api";

export class ApiError extends Error {
  readonly status: number;
  readonly body: ErrorBody;

  constructor(status: number, body: ErrorBody) {
    super(body.error);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    throw new ApiError(response.status, (await response.json()) as ErrorBody);
  }
  return (await response.json()) as T;
}

export function fetchInstitutions(kind: "cc" | "target"): Promise<{ institutions: InstitutionRow[] }> {
  return request(`/api/institutions?kind=${kind}`);
}

export function fetchMajors(
  sendingId: number,
  receivingId: number,
): Promise<{ majors: MajorRow[] }> {
  return request(`/api/pairs/${sendingId}/${receivingId}/majors`);
}

export function searchCourses(
  institutionId: number,
  q: string,
): Promise<{ courses: CourseHit[] }> {
  return request(`/api/cc/${institutionId}/courses?q=${encodeURIComponent(q)}`);
}

export function createEvaluation(body: EvaluationRequestBody): Promise<Evaluation> {
  return request("/api/evaluations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function fetchEvaluation(evaluationId: string): Promise<Evaluation> {
  return request(`/api/evaluations/${encodeURIComponent(evaluationId)}`);
}
