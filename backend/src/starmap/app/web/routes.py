"""Every `/api/*` route (doc 01, "Routes").

Request models are HTTP-layer shapes, not domain contracts, so they live here
with `extra="forbid"`; the domain contracts stay in `contracts/`. All list
responses are wrapped in an object, never a bare array.

The vocabulary gate: `POST /api/evaluations` never trusts client units or
titles. The `cc_courses` projection supplies both, and a code outside the
projection becomes a typed `unresolved` finding via `build_evaluation`.
"""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from starmap.app.web.bundles import load_bundle
from starmap.app.web.errors import LlmUnavailableError, PetitionPendingError, error_body
from starmap.app.web.store import selection_key
from starmap.contracts.dedup import find_duplicates
from starmap.contracts.evaluation import Evaluation
from starmap.contracts.petition import Petition
from starmap.contracts.reason_codes import LlmReasonCode
from starmap.contracts.transcript_parse import TranscriptChip, TranscriptParse
from starmap.llm.petition_writer import SELECTABLE_BUCKETS, write_petition
from starmap.llm.transcript_parser import ChipResolver, parse_transcript
from starmap.retrieval.errors import InstitutionNotIndexedError
from starmap.retrieval.index import CourseIndex
from starmap.retrieval.resolve import resolve_course
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


# --- the LLM seam (docs/implementation-plans/llm-nodes/03-web-seam.md) -------
#
# Both POST routes are 202-then-poll: insert a `pending` row, schedule the
# node run on `BackgroundTasks`, return the job id. `app/web` importing
# `retrieval` and `llm` here is the composition root doing its job; `llm/`
# itself stays retrieval-free (decision 1).


class ParseRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=20000)
    sending_institution_id: int = Field(gt=0)


class PetitionRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    finding_positions: list[Annotated[int, Field(ge=0)]] = Field(
        min_length=1, max_length=MAX_COURSES
    )

    @model_validator(mode="after")
    def _check_positions_unique(self) -> "PetitionRequestBody":
        duplicates = find_duplicates(str(position) for position in self.finding_positions)
        if duplicates:
            raise ValueError(f"finding_positions contains duplicate positions: {duplicates}")
        return self


def chip_resolver(index: CourseIndex, institution_id: int) -> ChipResolver:
    """Adapt `resolve_course` to the node's `ChipResolver` seam."""

    def resolve(*, code: str | None, title: str | None) -> TranscriptChip | None:
        resolution = resolve_course(index, institution_id, code=code, title=title)
        status = resolution.status
        if status == "unresolved":
            return None
        assert resolution.course_code is not None
        assert resolution.title is not None
        assert resolution.units_min is not None
        assert resolution.units_max is not None
        return TranscriptChip(
            course_code=resolution.course_code,
            title=resolution.title,
            units_min=resolution.units_min,
            units_max=resolution.units_max,
            resolution=status,
        )

    return resolve


def run_parse_job(
    state: Any, *, parse_id: str, sid: str, sending_institution_id: int, text: str
) -> None:
    """Background body for one transcript parse; the response is already out.

    The catch-all is a belt over the node's never-raise contract: an
    unexpected exception finishes the row as `failed` instead of leaving a
    `pending` row to silently outlive its poller.
    """
    try:
        parse = parse_transcript(
            parse_id=parse_id,
            sending_institution_id=sending_institution_id,
            text=text,
            resolver=chip_resolver(state.index, sending_institution_id),
            engine=state.llm.transcript_engine,
            clock=state.clock,
        )
        state.parses.finish(parse)
    except Exception:
        state.parses.finish(
            TranscriptParse(
                parse_id=parse_id,
                sending_institution_id=sending_institution_id,
                status="failed",
                reason_code=LlmReasonCode.CALL_FAILED,
                chips=[],
                unresolved=[],
                created_at=state.clock.now(),
            )
        )


def run_petition_job(
    state: Any,
    *,
    petition_id: str,
    sid: str,
    evaluation: Evaluation,
    finding_positions: list[int],
    sending_name: str,
    receiving_name: str,
    major_label: str,
) -> None:
    """Background body for one petition draft; same catch-all belt as the parse job."""
    try:
        petition = write_petition(
            petition_id=petition_id,
            evaluation=evaluation,
            finding_positions=finding_positions,
            sending_name=sending_name,
            receiving_name=receiving_name,
            major_label=major_label,
            engine=state.llm.petition_engine,
            clock=state.clock,
        )
        state.petitions.finish(petition)
    except Exception:
        state.petitions.finish(
            Petition(
                petition_id=petition_id,
                evaluation_id=evaluation.evaluation_id,
                finding_positions=finding_positions,
                status="failed",
                reason_code=LlmReasonCode.CALL_FAILED,
                fallback=False,
                letter_text=None,
                cited=[],
                created_at=state.clock.now(),
            )
        )


def _prompt_names(state: Any, evaluation: Evaluation) -> tuple[str, str, str]:
    """(sending_name, receiving_name, major_label) from the articulation store.

    These lookups cannot miss for a stored evaluation; a miss is a programming
    error and may raise.
    """
    names = {
        institution.assist_id: institution.name
        for institution in state.articulation.load_institutions()
    }
    agreements = state.articulation.load_agreements_for_pair(
        evaluation.sending_institution_id, evaluation.receiving_institution_id
    )
    major_label = next(
        agreement.label for agreement in agreements if agreement.assist_key == evaluation.major_key
    )
    return (
        names[evaluation.sending_institution_id],
        names[evaluation.receiving_institution_id],
        major_label,
    )


@router.post("/evaluations/{evaluation_id}/petition", status_code=202, response_model=None)
def create_petition(
    request: Request,
    evaluation_id: str,
    body: PetitionRequestBody,
    background_tasks: BackgroundTasks,
) -> Response | dict[str, str]:
    """The locked precondition order: 404, then 422, then the two 409s."""
    state = request.app.state
    evaluation: Evaluation | None = state.evaluations.get(request.state.sid, evaluation_id)
    if evaluation is None:
        return JSONResponse(
            status_code=404, content=error_body("evaluation not found", "not_found")
        )
    invalid = [
        position
        for position in body.finding_positions
        if position >= len(evaluation.findings)
        or evaluation.findings[position].bucket not in SELECTABLE_BUCKETS
    ]
    if invalid:
        raise RequestValidationError(
            [
                {
                    "loc": ("body", "finding_positions"),
                    "msg": (
                        f"positions {invalid} do not reference an at-risk or "
                        f"no-articulation finding of this evaluation"
                    ),
                    "type": "value_error",
                }
            ]
        )
    if state.llm is None:
        raise LlmUnavailableError()
    key = selection_key(body.finding_positions)
    if state.petitions.pending_exists(
        request.state.sid, evaluation.evaluation_id, key, now=state.clock.now()
    ):
        raise PetitionPendingError(evaluation.evaluation_id)
    sending_name, receiving_name, major_label = _prompt_names(state, evaluation)
    positions = sorted(body.finding_positions)
    petition_id = state.ids.new_id("pet")
    state.petitions.put(
        request.state.sid,
        Petition(
            petition_id=petition_id,
            evaluation_id=evaluation.evaluation_id,
            finding_positions=positions,
            status="pending",
            created_at=state.clock.now(),
        ),
    )
    background_tasks.add_task(
        run_petition_job,
        state,
        petition_id=petition_id,
        sid=request.state.sid,
        evaluation=evaluation,
        finding_positions=positions,
        sending_name=sending_name,
        receiving_name=receiving_name,
        major_label=major_label,
    )
    return {"petition_id": petition_id}


@router.get("/petitions/{petition_id}", response_model=None)
def get_petition(request: Request, petition_id: str) -> Response | dict[str, Any]:
    petition: Petition | None = request.app.state.petitions.get(request.state.sid, petition_id)
    if petition is None:
        return JSONResponse(status_code=404, content=error_body("petition not found", "not_found"))
    # Exactly doc 05's poll shape; internal fields never reach the wire.
    return {
        "status": petition.status,
        "reason_code": None if petition.reason_code is None else petition.reason_code.value,
        "fallback": petition.fallback,
        "letter_text": petition.letter_text,
        "cited": [
            {"course_code": entry.course_code, "finding_position": entry.finding_position}
            for entry in petition.cited
        ],
    }


@router.post("/transcript/parse", status_code=202)
def create_parse(
    request: Request, body: ParseRequestBody, background_tasks: BackgroundTasks
) -> dict[str, str]:
    state = request.app.state
    if state.llm is None:
        raise LlmUnavailableError()
    # The institution probe (doc 03): the 409 must happen before the 202, and
    # an empty `cc_courses` projection is exactly "nothing to resolve against".
    if not state.articulation.load_cc_courses(body.sending_institution_id):
        raise InstitutionNotIndexedError(body.sending_institution_id)
    parse_id = state.ids.new_id("parse")
    state.parses.put(
        request.state.sid,
        TranscriptParse(
            parse_id=parse_id,
            sending_institution_id=body.sending_institution_id,
            status="pending",
            created_at=state.clock.now(),
        ),
    )
    background_tasks.add_task(
        run_parse_job,
        state,
        parse_id=parse_id,
        sid=request.state.sid,
        sending_institution_id=body.sending_institution_id,
        text=body.text,
    )
    return {"parse_id": parse_id}


@router.get("/transcript/{parse_id}", response_model=None)
def get_parse(request: Request, parse_id: str) -> Response | dict[str, Any]:
    parse: TranscriptParse | None = request.app.state.parses.get(request.state.sid, parse_id)
    if parse is None:
        return JSONResponse(status_code=404, content=error_body("parse not found", "not_found"))
    return {
        "status": parse.status,
        "reason_code": None if parse.reason_code is None else parse.reason_code.value,
        "chips": [
            {
                "course_code": chip.course_code,
                "title": chip.title,
                "units_min": chip.units_min,
                "units_max": chip.units_max,
                "resolution": chip.resolution,
            }
            for chip in parse.chips
        ],
        "unresolved": [
            {"proposed_code": entry.proposed_code, "proposed_title": entry.proposed_title}
            for entry in parse.unresolved
        ],
    }
