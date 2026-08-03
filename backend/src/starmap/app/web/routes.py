"""Every `/api/*` route (doc 01, "Routes").

Request models are HTTP-layer shapes, not domain contracts, so they live here
with `extra="forbid"`; the domain contracts stay in `contracts/`. All list
responses are wrapped in an object, never a bare array.

The vocabulary gate: `POST /api/evaluations` never trusts client units or
titles. The `cc_courses` projection supplies both, and a code outside the
projection becomes a typed `unresolved` finding via `build_evaluation`.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from starmap.app.web.bundles import load_bundle
from starmap.app.web.errors import error_body
from starmap.contracts.dedup import find_duplicates
from starmap.contracts.evaluation import Evaluation
from starmap.transfer.arbitrage import build_arbitrage
from starmap.transfer.evaluate import AgreementBundle, CourseRequest, build_evaluation

router = APIRouter(prefix="/api")

# Locked server-side: no client override (doc 01, autocomplete).
AUTOCOMPLETE_K = 8
MAX_COURSES = 60


class CourseEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_code: str = Field(min_length=1, max_length=32)

    @field_validator("course_code")
    @classmethod
    def _normalize(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("course_code is empty after stripping whitespace")
        return normalized


class EvaluationRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sending_institution_id: int = Field(gt=0)
    receiving_institution_id: int = Field(gt=0)
    major_key: str = Field(min_length=1, max_length=200)
    courses: list[CourseEntry] = Field(min_length=1, max_length=MAX_COURSES)

    @model_validator(mode="after")
    def _check_courses_unique(self) -> "EvaluationRequestBody":
        duplicates = find_duplicates(entry.course_code for entry in self.courses)
        if duplicates:
            raise ValueError(f"courses contains duplicate course codes: {duplicates}")
        return self


@router.get("/institutions")
def list_institutions(
    request: Request, kind: Annotated[Literal["cc", "target"], Query()]
) -> dict[str, list[dict[str, Any]]]:
    wanted = {"cc"} if kind == "cc" else {"uc", "csu"}
    rows = [
        institution
        for institution in request.app.state.articulation.load_institutions()
        if institution.kind in wanted
    ]
    rows.sort(key=lambda institution: (institution.name, institution.assist_id))
    return {
        "institutions": [
            {
                "assist_id": institution.assist_id,
                "code": institution.code,
                "name": institution.name,
                "kind": institution.kind,
            }
            for institution in rows
        ]
    }


@router.get("/pairs/{sending_id}/{receiving_id}/majors")
def list_majors(
    request: Request, sending_id: int, receiving_id: int
) -> dict[str, list[dict[str, Any]]]:
    agreements = request.app.state.articulation.load_agreements_for_pair(sending_id, receiving_id)
    majors = [agreement for agreement in agreements if agreement.category == "major"]
    majors.sort(key=lambda agreement: (agreement.label, agreement.assist_key))
    return {
        "majors": [
            {
                "assist_key": agreement.assist_key,
                "label": agreement.label,
                "year_label": agreement.academic_year_label,
            }
            for agreement in majors
        ]
    }


@router.get("/cc/{institution_id}/courses")
def autocomplete_courses(
    request: Request, institution_id: int, q: Annotated[str, Query(min_length=1)]
) -> dict[str, list[dict[str, Any]]]:
    query = q.strip()
    if not query:
        raise RequestValidationError(
            [
                {
                    "loc": ("query", "q"),
                    "msg": "q is empty after stripping whitespace",
                    "type": "value_error",
                }
            ]
        )
    hits = request.app.state.index.search(institution_id, query, k=AUTOCOMPLETE_K)
    return {
        "courses": [
            {
                "course_code": hit.course_code,
                "title": hit.title,
                "units_min": hit.units_min,
                "units_max": hit.units_max,
            }
            for hit in hits
        ]
    }


def _cached_bundle(state: Any, sending: int, receiving: int, major_key: str) -> AgreementBundle:
    """The DBs are read-only, so the cache never invalidates (doc 01)."""
    key = (sending, receiving, major_key)
    bundle: AgreementBundle | None = state.bundles.get(key)
    if bundle is None:
        bundle = load_bundle(state.articulation, *key)
        state.bundles[key] = bundle
    return bundle


@router.post("/evaluations")
def create_evaluation(request: Request, body: EvaluationRequestBody) -> dict[str, Any]:
    state = request.app.state
    bundle = _cached_bundle(
        state, body.sending_institution_id, body.receiving_institution_id, body.major_key
    )
    projection = {
        row.course_code: row
        for row in state.articulation.load_cc_courses(body.sending_institution_id)
    }
    requests = [
        CourseRequest(
            course_code=entry.course_code,
            units=row.units_min,
            title=row.title,
        )
        if (row := projection.get(entry.course_code)) is not None
        else CourseRequest(course_code=entry.course_code)
        for entry in body.courses
    ]
    evaluation = build_evaluation(
        requests=requests,
        vocabulary=frozenset(projection),
        bundle=bundle,
        id_generator=state.ids,
        clock=state.clock,
        cost_table=state.costs,
    )
    state.evaluations.put(request.state.sid, evaluation)
    return evaluation.model_dump(mode="json")


@router.get("/arbitrage", response_model=None)
def get_arbitrage(
    request: Request, evaluation_id: Annotated[str, Query(min_length=1)]
) -> Response | dict[str, Any]:
    """Mode B over a stored evaluation: rebuild the bundle from the stored
    pair + major key, rank server-side; the client never re-sorts."""
    state = request.app.state
    evaluation: Evaluation | None = state.evaluations.get(request.state.sid, evaluation_id)
    if evaluation is None:
        # Uniform across unknown ids and other sessions' ids (doc 01).
        return JSONResponse(
            status_code=404, content=error_body("evaluation not found", "not_found")
        )
    bundle = _cached_bundle(
        state,
        evaluation.sending_institution_id,
        evaluation.receiving_institution_id,
        evaluation.major_key,
    )
    rows, omitted_no_rate = build_arbitrage(evaluation, bundle, state.costs)
    target_rate = (
        state.costs.target_rate(evaluation.receiving_institution_id)
        if state.costs is not None
        else None
    )
    return {
        "rows": [row.model_dump(mode="json") for row in rows],
        "omitted_no_rate": omitted_no_rate,
        "cc_per_unit": state.costs.cc_per_unit_default if state.costs is not None else None,
        "target_per_unit": target_rate,
    }


@router.get("/evaluations/{evaluation_id}", response_model=None)
def get_evaluation(request: Request, evaluation_id: str) -> Response | dict[str, Any]:
    evaluation: Evaluation | None = request.app.state.evaluations.get(
        request.state.sid, evaluation_id
    )
    if evaluation is None:
        # Uniform across unknown ids and other sessions' ids: never reveal
        # existence across sessions (doc 01).
        return JSONResponse(
            status_code=404, content=error_body("evaluation not found", "not_found")
        )
    return evaluation.model_dump(mode="json")
