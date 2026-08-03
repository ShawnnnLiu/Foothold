"""Two-stage decode of ASSIST payloads into the increment 4 contracts.

Stage A is the envelope: `{result, validationFailure, isSuccessful}` where five
of `result`'s fields are JSON-STRINGIFIED STRINGS that must be `json.loads`-ed a
second time (spike doc, "Agreement payload model"). `decode_envelope` and
`decode_field` are that stage, each with its own typed failure.

Stage B maps the decoded payload onto `Institution`, `Agreement`,
`Articulation`, `RequirementGroupAsset`, and the two course projections. Both
observed articulation list shapes go through one path: an entry carrying
`templateCellId` is the major-agreement template-cell wrapper (inner
articulation under `articulation`), anything else is a bare base-model entry
(dept). `position` is always the entry's index in the decoded array, because
that index is half the citation every finding carries.

Fault isolation is the point of this module. One poisoned articulation removes
one articulation, not the agreement; the failures come back as `Exclusion`
records on `NormalizedAgreement` rather than as raised exceptions, and the
build report prints every one of them (no silent drops). Only an unusable
ENVELOPE raises out of `normalize_agreement`, which excludes that one agreement
and leaves the corridor build running.

Two reason-code conventions, since the payload can fail contract validation in
places doc 02 does not enumerate one by one:

- a payload course that will not become a valid course row is
  `course_code_unparseable`, which is doc 02 step 2's "normalization failure"
  for the receiving-course mapping applied to every course row;
- any other contract-validation failure over payload-derived data is
  `envelope_invalid`, whose spec meaning ("the response envelope did not match
  the expected ASSIST shape") is exactly what a payload that will not fit its
  contract is.

Advisements were pinned in S9c from live corridor payloads (see
`advisement_texts`). Twelve levels feed it as of S9e: the four doc 02 locks
(articulation, sending-articulation, sending course group, sending course),
the three the S9c sweep added (`courseAttributes` on the articulation, and
`attributes` on template groups and template cells), and five a full-corridor
S9e sweep proved carry real prose the sample-based S9c sweep missed -
`seriesAttributes` on the articulation, `attributes` on template sections and
rows, and `courseAttributes`/`seriesAttributes` on template cells, the last of
which is the volume carrier ("Minimum grade required: B or better", 41,246
corridor entries). Two lists stay unread deliberately: `receivingAttributes`
mirrors the articulation-level lists verbatim, and `requirementAttributes`
sits only on `Requirement` cells, which already exclude their group.
On "No Course Articulated" rows ASSIST sends `null` rather than `[]` for its
attribute lists, so absent and empty must read the same.
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import ValidationError

from starmap.assist.errors import AssistNormalizeError
from starmap.contracts.agreement import (
    Agreement,
    AgreementCategory,
    RequirementGroupAsset,
    derive_agreement_id,
)
from starmap.contracts.articulation import Articulation, ReceivingCourse
from starmap.contracts.articulation_expr import (
    AllOf,
    AnyOf,
    ArticulationExpr,
    CourseLeaf,
    NoteLeaf,
)
from starmap.contracts.base import reject_control_chars
from starmap.contracts.cc_course import CcCourse
from starmap.contracts.codes import course_code_from_parts
from starmap.contracts.institution import Institution, InstitutionKind
from starmap.contracts.reason_codes import AssistBuildCode
from starmap.contracts.target_course import TargetCourse

# The five double-encoded `result` fields (spike doc). All five are decoded even
# though the institution envelopes are only an integrity check: a payload whose
# stringified fields do not decode is not a payload we normalize half of.
STRINGIFIED_FIELDS = (
    "receivingInstitution",
    "sendingInstitution",
    "academicYear",
    "templateAssets",
    "articulations",
)

# The pinned advisement entry shape (S9c, from live corridor payloads).
ADVISEMENT_TEXT_KEY = "content"
MAX_ADVISEMENT_LENGTH = 2000  # matches `AdvisementText` in contracts/articulation.py

COURSE_ITEM_TYPE = "Course"
SUPPORTED_ARTICULATION_TYPE = "Course"
# Several receiving courses that articulate only as a unit (S9d). 42,449
# corridor articulations and 49,634 template row cells carry this type; before
# S9d both were typed exclusions, which cost the artifact every sequence-based
# transfer rule in the corridor.
SERIES_ARTICULATION_TYPE = "Series"
MODELED_CELL_TYPES = (COURSE_ITEM_TYPE, SERIES_ARTICULATION_TYPE)
REQUIREMENT_GROUP_ASSET_TYPE = "RequirementGroup"
CONJUNCTION_INSTRUCTION_TYPE = "Conjunction"
DEFAULT_GROUP_CONJUNCTION = "And"

# "Complete the following", ASSIST's own rendering of a `Following` instruction.
# The payload carries exactly `{"type", "id", "selectionType"}` in all 39,434
# corridor instances: no `amount`, no `conjunction`, no selection semantics, so
# it means the same thing a null instruction does. `selectionType` is the gate,
# because 460 of those instances say `Select` rather than `Complete` and a
# selection rule is genuinely unmodeled (S9d; see doc 02).
FOLLOWING_INSTRUCTION_TYPE = "Following"
COMPLETE_SELECTION_TYPE = "Complete"

# The N-from selection rules, and the slice of their parameter space this build
# models (S9d; semantics corrected in S9e against rendered agreements). ASSIST
# renders every one as "Complete [at least] {amount} {amountUnitType} from
# {section letters joined by the instruction's own conjunction}", so the amount
# counts COURSES, never sections. The mapped slice becomes `select_courses`;
# every other combination stays a typed exclusion for the reasons in
# `docs/specs/agreement.schema.md`:
#
# - `UpTo` is a CAP ("complete up to 8.00 semester units"), not a requirement.
# - `Unit`/`SemesterUnit` count units, and the template has no unit arithmetic.
# - `Series`/`Sequence`/`CourseOrCombination`/`OrMoreCourses` denominate the
#   amount in objects the pool does not count.
# - `toAmountDeterminer` of `Any`/`Each` quantifies over a range.
# - An `NFromConjunction` area conjunction of `And` over SEVERAL sections
#   ("Complete 1 course from A and B") is ambiguous between "from each" and
#   "from the union"; over one section it names nothing (rendered "from A")
#   and the union reading is exact.
#
# `NFromFollowing` carries an amount and no unit or conjunction at all; "the
# following" is the group's own sections, so it maps on the union terms.
SELECTION_GROUP_CONJUNCTION = "Or"
AREA_SELECTION_TYPES = ("NFromArea", "NFromConjunction")
CONJUNCTION_SELECTION_TYPE = "NFromConjunction"
FOLLOWING_SELECTION_TYPE = "NFromFollowing"
SELECTABLE_AMOUNT_UNIT = "Course"
SELECTABLE_QUANTIFIERS = ("None", "AtLeast")
NEUTRAL_TO_AMOUNT_DETERMINERS = ("None", None)
INERT_AREA_CONJUNCTIONS = ("Or", None)

# `category` as `/api/institutions` publishes it; `isCommunityCollege` wins over
# both (spike implication 5), and anything else (observed: 5, private) is an
# unknown kind that is counted and skipped, never stored and never fatal.
KIND_FOR_CATEGORY: dict[int, InstitutionKind] = {1: "uc", 0: "csu"}


# --- what a normalize produces ----------------------------------------------


@dataclass(frozen=True, slots=True)
class Exclusion:
    """One thing the build refused to store, with the reason it refused."""

    assist_key: str
    position: int | None
    reason_code: AssistBuildCode
    detail: str


@dataclass(frozen=True, slots=True)
class NormalizedAgreement:
    agreement: Agreement
    articulations: tuple[Articulation, ...] = ()
    requirement_groups: tuple[RequirementGroupAsset, ...] = ()
    cc_courses: tuple[CcCourse, ...] = ()
    target_courses: tuple[TargetCourse, ...] = ()
    exclusions: tuple[Exclusion, ...] = ()


@dataclass(frozen=True, slots=True)
class AcademicYear:
    """A `/api/AcademicYears` row. The label is derived: the endpoint publishes
    only `{id, fallYear}`, while the store and `Agreement` both spell the year
    as `2025-2026`."""

    year_id: int
    label: str
    fall_year: int


# --- typed payload readers --------------------------------------------------


def _fail(message: str, code: AssistBuildCode) -> AssistNormalizeError:
    return AssistNormalizeError(message, reason_code=code)


def _as_dict(value: object, *, what: str, code: AssistBuildCode) -> dict[str, object]:
    if not isinstance(value, dict):
        raise _fail(f"ASSIST {what} was {type(value).__name__}, expected an object", code)
    return value


def _as_list(value: object, *, what: str, code: AssistBuildCode) -> list[object]:
    if not isinstance(value, list):
        raise _fail(f"ASSIST {what} was {type(value).__name__}, expected a list", code)
    return value


def _dicts(value: object, *, what: str, code: AssistBuildCode) -> list[dict[str, object]]:
    return [
        _as_dict(entry, what=f"{what} entry", code=code)
        for entry in _as_list(value, what=what, code=code)
    ]


def _by_position(entries: Iterable[dict[str, object]]) -> list[dict[str, object]]:
    """ASSIST publishes groups, sections, and rows out of order; `position` is
    the published order and therefore the deterministic one."""
    return sorted(entries, key=lambda entry: _position_of(entry))


def _position_of(entry: dict[str, object]) -> int:
    position = entry.get("position")
    return position if isinstance(position, int) else 0


def _validation_detail(error: ValidationError) -> str:
    """A compact one-line summary; payload values are ASSIST's public data, but
    a full pydantic report in a build log is noise rather than information."""
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
    )


# --- stage A: the envelope --------------------------------------------------


def decode_envelope(raw: object) -> dict[str, object]:
    """`{result, validationFailure, isSuccessful}` in, `result` out."""
    envelope = _as_dict(raw, what="agreement envelope", code=AssistBuildCode.ENVELOPE_INVALID)
    if envelope.get("isSuccessful") is not True:
        raise _fail(
            "ASSIST agreement envelope reported isSuccessful != true",
            AssistBuildCode.ENVELOPE_INVALID,
        )
    return _as_dict(
        envelope.get("result"), what="agreement result", code=AssistBuildCode.ENVELOPE_INVALID
    )


def decode_field(result: dict[str, object], name: str) -> object:
    """One stringified `result` field, decoded a second time.

    A null field is null (dept agreements carry `templateAssets: null`); the
    typed failure covers a field that is neither null nor a decodable string.
    """
    value = result.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _fail(
            f"ASSIST result field {name!r} was {type(value).__name__}, expected a JSON string",
            AssistBuildCode.FIELD_DECODE_FAILED,
        )
    try:
        return json.loads(value)
    except json.JSONDecodeError as error:
        raise _fail(
            f"ASSIST result field {name!r} did not decode as JSON",
            AssistBuildCode.FIELD_DECODE_FAILED,
        ) from error


def advisement_texts(attributes: object) -> list[str]:
    """ASSIST attribute entries in, advisement strings out.

    The shape was pinned in S9c from live corridor payloads, not guessed:
    a text advisement is exactly `{"content": str, "position": int}`, and the
    corridor publishes 11 distinct strings of it ("Minimum grade required: C or
    better", "Complete entire sequence at same institution prior to transfer",
    and so on). Absent or empty still means no advisements, because ASSIST
    sends `null` on "No Course Articulated" rows and `[]` elsewhere.

    ANYTHING else still raises `advisement_shape_unknown`, and that gate is
    load-bearing rather than vestigial: the same `advisements` field on
    template sections carries a completely different, STRUCTURED shape
    (`{"type": "NFollowing", "amount": 2.0, "selectionType": "Select", ...}`,
    i.e. "select 2 of the following"). That is a requirement rule, not prose.
    Flattening it to text would be an invention, and skipping it would leave a
    group reading as "complete all of" when it means "select 2 of", so the
    group is excluded and reported instead. Modelling those N-from semantics is
    deferred (see the S9c notes).

    Text is taken verbatim apart from an outer strip: never paraphrased, never
    merged, never truncated. An entry that survives the shape check but could
    not become an `AdvisementText` is a shape failure too, not a silent drop.
    """
    if attributes is None or attributes == []:
        return []
    entries = _as_list(attributes, what="attributes", code=AssistBuildCode.ADVISEMENT_SHAPE_UNKNOWN)
    texts: list[tuple[int, str]] = []
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get(ADVISEMENT_TEXT_KEY), str):
            raise _fail(
                f"ASSIST attribute entry {_shape_of(entry)} is not the pinned advisement shape "
                f"{{{ADVISEMENT_TEXT_KEY!r}, 'position'}}",
                AssistBuildCode.ADVISEMENT_SHAPE_UNKNOWN,
            )
        content = str(entry[ADVISEMENT_TEXT_KEY]).strip()
        if not content or len(content) > MAX_ADVISEMENT_LENGTH:
            raise _fail(
                f"ASSIST advisement text of length {len(content)} cannot become an "
                f"AdvisementText (1..{MAX_ADVISEMENT_LENGTH} characters)",
                AssistBuildCode.ADVISEMENT_SHAPE_UNKNOWN,
            )
        try:
            reject_control_chars(content)
        except ValueError as error:
            raise _fail(
                "ASSIST advisement text carried control characters",
                AssistBuildCode.ADVISEMENT_SHAPE_UNKNOWN,
            ) from error
        texts.append((_position_of(entry), content))
    # `position` is ASSIST's published order; ties keep list order, so the
    # result is a pure function of the payload.
    return [content for _, content in sorted(texts, key=lambda pair: pair[0])]


def _shape_of(entry: object) -> str:
    """A compact description of an unexpected entry, for the exclusion detail."""
    if isinstance(entry, dict):
        return f"with keys {sorted(str(key) for key in entry)}"
    return f"of type {type(entry).__name__}"


# --- stage B: institutions and years ----------------------------------------


def normalize_institution(raw: object) -> Institution | None:
    """One `/api/institutions` entry, or None for a kind outside the corridor.

    None is not a failure: 33 of the 181 published institutions are private
    (category 5) and simply are not part of a CCC -> UC/CSU corridor. The build
    report counts them under `institution_kind_unknown`.
    """
    entry = _as_dict(raw, what="institution", code=AssistBuildCode.ENVELOPE_INVALID)
    kind = _institution_kind(entry)
    if kind is None:
        return None
    code = entry.get("code")
    try:
        return Institution.model_validate(
            {
                "assist_id": entry.get("id"),
                "code": code.strip() if isinstance(code, str) else code,
                "name": _latest_name(entry),
                "kind": kind,
            }
        )
    except ValidationError as error:
        raise _fail(
            f"ASSIST institution {entry.get('id')!r} failed contract validation: "
            f"{_validation_detail(error)}",
            AssistBuildCode.ENVELOPE_INVALID,
        ) from error


def _institution_kind(entry: dict[str, object]) -> InstitutionKind | None:
    if entry.get("isCommunityCollege") is True:
        return "cc"
    category = entry.get("category")
    if isinstance(category, int) and not isinstance(category, bool):
        return KIND_FOR_CATEGORY.get(category)
    return None


def _latest_name(entry: dict[str, object]) -> object:
    """The `names[]` entry with the highest `fromYear`; absent reads as 0."""
    names = _dicts(
        entry.get("names"), what="institution names", code=AssistBuildCode.ENVELOPE_INVALID
    )
    if not names:
        return None

    def from_year(name: dict[str, object]) -> int:
        value = name.get("fromYear")
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    return max(names, key=from_year).get("name")


def normalize_academic_years(raw: object) -> list[AcademicYear]:
    """`/api/AcademicYears` in, store rows out, sorted by year id."""
    years: list[AcademicYear] = []
    for entry in _dicts(raw, what="academic years", code=AssistBuildCode.ENVELOPE_INVALID):
        year_id = entry.get("id")
        fall_year = entry.get("fallYear")
        if not isinstance(year_id, int) or not isinstance(fall_year, int):
            raise _fail(
                "ASSIST academic year entry had no integer id and fallYear",
                AssistBuildCode.ENVELOPE_INVALID,
            )
        years.append(
            AcademicYear(year_id=year_id, label=f"{fall_year}-{fall_year + 1}", fall_year=fall_year)
        )
    return sorted(years, key=lambda year: year.year_id)


# --- stage B: agreements ----------------------------------------------------


def normalize_agreement(
    raw: object,
    *,
    assist_key: str,
    category: AgreementCategory,
    label: str,
    sending_id: int,
    receiving_id: int,
) -> NormalizedAgreement:
    """One agreement payload in, contracts plus typed exclusions out.

    Raises `AssistNormalizeError` only when the envelope itself is unusable;
    everything below the envelope is isolated into `exclusions`.
    """
    result = decode_envelope(raw)
    decoded = {name: decode_field(result, name) for name in STRINGIFIED_FIELDS}
    agreement = _agreement(
        result,
        decoded["academicYear"],
        assist_key=assist_key,
        category=category,
        label=label,
        sending_id=sending_id,
        receiving_id=receiving_id,
    )

    articulations: list[Articulation] = []
    cc_courses: list[CcCourse] = []
    target_courses: list[TargetCourse] = []
    exclusions: list[Exclusion] = []

    entries = _dicts(
        decoded["articulations"],
        what="articulations",
        code=AssistBuildCode.ENVELOPE_INVALID,
    )
    for position, entry in enumerate(entries):
        # Per-articulation isolation: an exclusion removes one articulation.
        try:
            articulation, sending, receiving = _articulation(
                entry,
                agreement_id=agreement.agreement_id,
                position=position,
                sending_id=sending_id,
                receiving_id=receiving_id,
            )
        except AssistNormalizeError as error:
            exclusions.append(
                Exclusion(assist_key, position, error.assist_reason_code, error.message)
            )
            continue
        articulations.append(articulation)
        cc_courses.extend(sending)
        target_courses.extend(receiving)

    groups, group_courses, group_exclusions = _requirement_groups(
        decoded["templateAssets"], assist_key=assist_key, receiving_id=receiving_id
    )
    target_courses.extend(group_courses)
    exclusions.extend(group_exclusions)

    return NormalizedAgreement(
        agreement=agreement,
        articulations=tuple(articulations),
        requirement_groups=tuple(groups),
        cc_courses=tuple(cc_courses),
        target_courses=tuple(target_courses),
        exclusions=tuple(exclusions),
    )


def _agreement(
    result: dict[str, object],
    academic_year: object,
    *,
    assist_key: str,
    category: AgreementCategory,
    label: str,
    sending_id: int,
    receiving_id: int,
) -> Agreement:
    year = _as_dict(academic_year, what="academicYear", code=AssistBuildCode.ENVELOPE_INVALID)
    try:
        return Agreement.model_validate(
            {
                "agreement_id": derive_agreement_id(assist_key),
                "assist_key": assist_key,
                "category": category,
                "sending_institution_id": sending_id,
                "receiving_institution_id": receiving_id,
                "academic_year_id": year.get("id"),
                "academic_year_label": year.get("code"),
                "label": label,
                "publish_date": result.get("publishDate"),
            }
        )
    except ValidationError as error:
        raise _fail(
            f"ASSIST agreement {assist_key!r} failed contract validation: "
            f"{_validation_detail(error)}",
            AssistBuildCode.ENVELOPE_INVALID,
        ) from error


def _articulation(
    entry: dict[str, object],
    *,
    agreement_id: str,
    position: int,
    sending_id: int,
    receiving_id: int,
) -> tuple[Articulation, list[CcCourse], list[TargetCourse]]:
    """One articulation entry, both list shapes, into one contract."""
    template_cell_id = entry.get("templateCellId")
    inner = (
        _as_dict(
            entry.get("articulation"),
            what="template-cell articulation",
            code=AssistBuildCode.ARTICULATION_TYPE_UNSUPPORTED,
        )
        if template_cell_id is not None
        else entry
    )
    kind = inner.get("type")
    receiving_course = None
    receiving_series = None
    if kind == SERIES_ARTICULATION_TYPE:
        receiving_series, target_courses = _receiving_series(
            inner.get("series"), receiving_id=receiving_id
        )
    elif kind == SUPPORTED_ARTICULATION_TYPE:
        receiving_raw = _as_dict(
            inner.get("course"),
            what="receiving course",
            code=AssistBuildCode.COURSE_CODE_UNPARSEABLE,
        )
        receiving_course = _course_row(ReceivingCourse, receiving_raw, institution_id=None)
        target_courses = [_course_row(TargetCourse, receiving_raw, institution_id=receiving_id)]
    else:
        raise _fail(
            f"ASSIST articulation at position {position} carries unsupported type {kind!r}",
            AssistBuildCode.ARTICULATION_TYPE_UNSUPPORTED,
        )

    cc_courses: list[CcCourse] = []
    sending_expr, no_articulation_reason = _sending(
        inner.get("sendingArticulation"), sending_id=sending_id, cc_courses=cc_courses
    )

    advisements = [
        *advisement_texts(inner.get("attributes")),
        # `courseAttributes` sits beside `attributes` and carries real
        # advisements ("Articulation is subject to placement by proficiency
        # exam"); before S9c measured that, it was read by nothing at all.
        # `seriesAttributes` is its Series-articulation sibling ("Departmental
        # credit limitation applies", 2,935 corridor entries), unread until
        # S9e. `receivingAttributes` mirrors these lists verbatim and stays
        # unread deliberately.
        *advisement_texts(inner.get("courseAttributes")),
        *advisement_texts(inner.get("seriesAttributes")),
        *_sending_advisements(inner.get("sendingArticulation")),
    ]
    try:
        articulation = Articulation.model_validate(
            {
                "agreement_id": agreement_id,
                "position": position,
                "template_cell_id": template_cell_id,
                "receiving_course": receiving_course,
                "receiving_series": receiving_series,
                "sending_expr": sending_expr,
                "no_articulation_reason": no_articulation_reason,
                "advisements": advisements,
            }
        )
    except ValidationError as error:
        raise _fail(
            f"ASSIST articulation at position {position} failed contract validation: "
            f"{_validation_detail(error)}",
            AssistBuildCode.ENVELOPE_INVALID,
        ) from error
    return articulation, cc_courses, target_courses


def _receiving_series(
    raw: object, *, receiving_id: int
) -> tuple[dict[str, object], list[TargetCourse]]:
    """A `Series` articulation's receiving side: several courses as one unit.

    Every course in the sequence still projects into `target_courses`, because
    that projection is the receiving-side vocabulary and a course does not stop
    existing for being articulated only as part of a sequence.
    """
    series = _as_dict(raw, what="series", code=AssistBuildCode.ARTICULATION_TYPE_UNSUPPORTED)
    entries = _dicts(
        series.get("courses"),
        what="series courses",
        code=AssistBuildCode.ARTICULATION_TYPE_UNSUPPORTED,
    )
    return (
        {
            "name": name.strip() if isinstance(name := series.get("name"), str) else name,
            "conjunction": series.get("conjunction"),
            "courses": [
                _course_row(ReceivingCourse, entry, institution_id=None) for entry in entries
            ],
        },
        [_course_row(TargetCourse, entry, institution_id=receiving_id) for entry in entries],
    )


def _sending_advisements(sending: object) -> list[str]:
    if not isinstance(sending, dict):
        return []
    return advisement_texts(sending.get("attributes"))


def _sending(
    sending: object, *, sending_id: int, cc_courses: list[CcCourse]
) -> tuple[ArticulationExpr | None, str | None]:
    """The transfer rule: an expression tree, or "No Course Articulated".

    Both encodings of "no articulation" mean the same thing (overview doc
    payload facts): a null `sendingArticulation` and an empty `items` list.
    """
    if sending is None:
        return None, None
    rule = _as_dict(
        sending, what="sendingArticulation", code=AssistBuildCode.ARTICULATION_TYPE_UNSUPPORTED
    )
    groups = _by_position(
        _dicts(
            rule.get("items"),
            what="sending course groups",
            code=AssistBuildCode.ARTICULATION_TYPE_UNSUPPORTED,
        )
    )
    if not groups:
        reason = rule.get("noArticulationReason")
        return None, reason if isinstance(reason, str) and reason else None

    nodes = [_group_node(group, sending_id=sending_id, cc_courses=cc_courses) for group in groups]
    return _join_groups(nodes, rule.get("courseGroupConjunctions")), None


def _group_node(
    group: dict[str, object], *, sending_id: int, cc_courses: list[CcCourse]
) -> ArticulationExpr:
    """One sending course group: its courses, joined by `courseConjunction`.

    Advisement notes are appended INSIDE the group node, so a note can never
    be lost between the group and its joiner. Group-level texts come first,
    then course-level texts in course order, which fixes the order without
    changing the semantics.
    """
    leaves: list[ArticulationExpr] = []
    notes: list[ArticulationExpr] = [
        NoteLeaf(note=text) for text in advisement_texts(group.get("attributes"))
    ]
    items = _by_position(
        _dicts(
            group.get("items"),
            what="sending group items",
            code=AssistBuildCode.ARTICULATION_TYPE_UNSUPPORTED,
        )
    )
    for item in items:
        if item.get("type") != COURSE_ITEM_TYPE:
            raise _fail(
                f"ASSIST sending group item carries unsupported type {item.get('type')!r}",
                AssistBuildCode.ARTICULATION_TYPE_UNSUPPORTED,
            )
        cc_course = _course_row(CcCourse, item, institution_id=sending_id)
        cc_courses.append(cc_course)
        leaves.append(CourseLeaf(course=cc_course.course_code))
        notes.extend(NoteLeaf(note=text) for text in advisement_texts(item.get("attributes")))

    if not leaves:
        raise _fail(
            "ASSIST sending course group held no course items",
            AssistBuildCode.ARTICULATION_TYPE_UNSUPPORTED,
        )
    if len(leaves) == 1:
        # A lone course stands alone; a lone course plus notes is an `all`,
        # never an `any`, so no note can be satisfied by taking the course.
        return leaves[0] if not notes else AllOf(all=[leaves[0], *notes])

    conjunction = group.get("courseConjunction")
    children = [*leaves, *notes]
    if conjunction == "And":
        return AllOf(all=children)
    if conjunction == "Or":
        return AnyOf(any=children)
    raise _fail(
        f"ASSIST sending course group carries courseConjunction {conjunction!r}, which the "
        f"expression mapping cannot express",
        AssistBuildCode.MIXED_GROUP_CONJUNCTION,
    )


def _join_groups(nodes: list[ArticulationExpr], conjunctions: object) -> ArticulationExpr:
    """Join two or more group nodes by their `courseGroupConjunctions`.

    Only `Or` is observed in the captures. A mixed set cannot be expressed as
    one node, and an empty set for a multi-group rule does not say how to join
    them; both are the same typed exclusion rather than a guess.
    """
    if len(nodes) == 1:
        return nodes[0]
    kinds = {
        entry.get("groupConjunction")
        for entry in _dicts(
            conjunctions,
            what="courseGroupConjunctions",
            code=AssistBuildCode.MIXED_GROUP_CONJUNCTION,
        )
    }
    if kinds == {"Or"}:
        return AnyOf(any=nodes)
    if kinds == {"And"}:
        return AllOf(all=nodes)
    raise _fail(
        f"ASSIST sending articulation joins {len(nodes)} groups with conjunctions "
        f"{sorted(str(kind) for kind in kinds)}, which the expression mapping cannot express",
        AssistBuildCode.MIXED_GROUP_CONJUNCTION,
    )


# --- stage B: template assets -----------------------------------------------


def _requirement_groups(
    assets: object, *, assist_key: str, receiving_id: int
) -> tuple[list[RequirementGroupAsset], list[TargetCourse], list[Exclusion]]:
    """The `RequirementGroup` assets of a major agreement, one group isolated.

    `GeneralTitle` and `GeneralText` assets are prose rather than requirements
    and are dropped for v1 (doc 02). Dept agreements carry no assets at all.
    """
    if assets is None:
        return [], [], []
    entries = [
        entry
        for entry in _dicts(assets, what="templateAssets", code=AssistBuildCode.ENVELOPE_INVALID)
        if entry.get("type") == REQUIREMENT_GROUP_ASSET_TYPE
    ]
    groups: list[RequirementGroupAsset] = []
    courses: list[TargetCourse] = []
    exclusions: list[Exclusion] = []
    for entry in _by_position(entries):
        position = _position_of(entry)
        try:
            group, group_courses = _requirement_group(entry, receiving_id=receiving_id)
        except AssistNormalizeError as error:
            exclusions.append(
                Exclusion(
                    assist_key,
                    position,
                    error.assist_reason_code,
                    f"template requirement group: {error.message}",
                )
            )
            continue
        groups.append(group)
        courses.extend(group_courses)
    return groups, courses, exclusions


def _requirement_group(
    entry: dict[str, object], *, receiving_id: int
) -> tuple[RequirementGroupAsset, list[TargetCourse]]:
    # Both group-level lists: ASSIST publishes the prose under `attributes`
    # ("Minimum grade required: C or better") and keeps `advisements` for the
    # structured N-from rules, which stay a typed exclusion.
    advisements = [
        *advisement_texts(entry.get("advisements")),
        *advisement_texts(entry.get("attributes")),
    ]
    sections: list[dict[str, object]] = []
    courses: list[TargetCourse] = []
    raw_sections = _by_position(
        _dicts(
            entry.get("sections"),
            what="template sections",
            code=AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
        )
    )
    for section in raw_sections:
        advisements.extend(advisement_texts(section.get("advisements")))
        advisements.extend(advisement_texts(section.get("attributes")))
        cells: list[dict[str, object]] = []
        rows = _by_position(
            _dicts(
                section.get("rows"),
                what="template rows",
                code=AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
            )
        )
        for row in rows:
            advisements.extend(advisement_texts(row.get("attributes")))
            cell = _template_cell(row)
            # Cell-level prose belongs to the group: `TemplateCell` carries the
            # join key and the course only. `courseAttributes` is the volume
            # carrier ("Minimum grade required: B or better", 41,246 corridor
            # entries); before S9e nothing read it, nor the row and section
            # `attributes` above, nor `seriesAttributes` - all silent drops.
            advisements.extend(advisement_texts(cell.get("attributes")))
            advisements.extend(advisement_texts(cell.get("courseAttributes")))
            advisements.extend(advisement_texts(cell.get("seriesAttributes")))
            if cell.get("type") == SERIES_ARTICULATION_TYPE:
                series, series_courses = _receiving_series(
                    cell.get("series"), receiving_id=receiving_id
                )
                cells.append({"cell_id": cell.get("id"), "series": series})
                courses.extend(series_courses)
                continue
            course_raw = _as_dict(
                cell.get("course"),
                what="template cell course",
                code=AssistBuildCode.COURSE_CODE_UNPARSEABLE,
            )
            cells.append(
                {
                    "cell_id": cell.get("id"),
                    "course": _course_row(ReceivingCourse, course_raw, institution_id=None),
                }
            )
            courses.append(_course_row(TargetCourse, course_raw, institution_id=receiving_id))
        sections.append({"position": _position_of(section), "cells": cells})

    conjunction, select_courses = _group_rule(entry.get("instruction"), section_count=len(sections))
    try:
        group = RequirementGroupAsset.model_validate(
            {
                "group_id": entry.get("groupId"),
                "position": _position_of(entry),
                "conjunction": conjunction,
                "select_courses": select_courses,
                "sections": sections,
                "advisements": advisements,
            }
        )
    except ValidationError as error:
        raise _fail(
            f"template requirement group failed contract validation: {_validation_detail(error)}",
            AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
        ) from error
    return group, courses


def _template_cell(row: dict[str, object]) -> dict[str, object]:
    """Every observed row holds exactly one `Course` or `Series` cell.

    `Requirement`, `GeneralEducation` and `CALGETC` cells remain unmodeled and
    take their group with them, because a row this build cannot render would
    otherwise silently shrink the requirement a student is shown.
    """
    cells = _dicts(
        row.get("cells"), what="template cells", code=AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED
    )
    modeled = [cell for cell in cells if cell.get("type") in MODELED_CELL_TYPES]
    if len(cells) != 1 or len(modeled) != 1:
        raise _fail(
            f"template row holds {len(cells)} cells of which {len(modeled)} are modeled "
            f"({', '.join(MODELED_CELL_TYPES)}); exactly one is the only modeled shape",
            AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
        )
    return modeled[0]


def _group_rule(instruction: object, *, section_count: int) -> tuple[str, int | None]:
    """The group's `(conjunction, select_courses)` pair.

    A null instruction is an implicit `And`, and so is `Following`; a
    `Conjunction` instruction carries the real one; a selection rule that
    counts COURSES becomes `("Or", n)`, meaning n courses from the union of
    the sections. Any other shape is excluded rather than guessed at, because
    the two available fallbacks are both wrong in ways that reach a student:
    storing it as `And` would say they owe every section, and storing it as
    `Or` that any single one suffices.

    `section_count` gates the one ambiguity: an `NFromConjunction` whose own
    area conjunction is `And` renders as "Complete 1 course from A and B" when
    the group has several sections, which could mean one course from each or
    one from the union, so it is excluded; with one section it renders "from
    A" and the union reading is exact.
    """
    if instruction is None:
        return DEFAULT_GROUP_CONJUNCTION, None
    entry = _as_dict(
        instruction,
        what="template group instruction",
        code=AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
    )
    kind = entry.get("type")
    if kind == FOLLOWING_INSTRUCTION_TYPE:
        selection = entry.get("selectionType")
        if selection != COMPLETE_SELECTION_TYPE:
            raise _fail(
                f"template group Following instruction carries selectionType {selection!r}, "
                f"which selects rather than completes",
                AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
            )
        return DEFAULT_GROUP_CONJUNCTION, None
    if kind in AREA_SELECTION_TYPES or kind == FOLLOWING_SELECTION_TYPE:
        amount = _selection_amount(entry, kind)
        area_conjunction = entry.get("conjunction")
        if (
            kind == CONJUNCTION_SELECTION_TYPE
            and area_conjunction not in INERT_AREA_CONJUNCTIONS
            and section_count > 1
        ):
            raise _fail(
                f"template group {kind!r} selection rule joins {section_count} sections with "
                f"area conjunction {area_conjunction!r}, which is ambiguous between one pool "
                f"and one amount per section",
                AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
            )
        return SELECTION_GROUP_CONJUNCTION, amount
    if kind != CONJUNCTION_INSTRUCTION_TYPE:
        raise _fail(
            f"template group instruction carries type {kind!r}, which is outside "
            f"the modeled asset shapes",
            AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
        )
    conjunction = entry.get("conjunction")
    if not isinstance(conjunction, str):
        raise _fail(
            "template group Conjunction instruction carried no string conjunction",
            AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
        )
    return conjunction, None


def _selection_amount(entry: dict[str, object], kind: object) -> int:
    """How many courses an N-from group needs, when the rule counts courses."""
    if kind != FOLLOWING_SELECTION_TYPE:
        unit = entry.get("amountUnitType")
        quantifier = entry.get("amountQuantifier")
        determiner = entry.get("toAmountDeterminer")
        if (
            unit != SELECTABLE_AMOUNT_UNIT
            or quantifier not in SELECTABLE_QUANTIFIERS
            or determiner not in NEUTRAL_TO_AMOUNT_DETERMINERS
        ):
            raise _fail(
                f"template group {kind!r} selection rule counts {quantifier!r} {unit!r} "
                f"with toAmountDeterminer {determiner!r}, which this build does not model",
                AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
            )
    amount = entry.get("amount")
    if not isinstance(amount, int | float) or isinstance(amount, bool) or amount != int(amount):
        raise _fail(
            f"template group selection rule carried a non-integral amount {amount!r}",
            AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
        )
    if int(amount) < 1:
        raise _fail(
            f"template group selection rule carried amount {amount!r}, expected at least 1",
            AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED,
        )
    return int(amount)


# --- course rows and the projection gate ------------------------------------


def _course_row[CourseRow: (ReceivingCourse, CcCourse, TargetCourse)](
    model: type[CourseRow], raw: dict[str, object], *, institution_id: int | None
) -> CourseRow:
    """The single payload-course-to-contract mapping for all three course rows.

    `ReceivingCourse` is the one without an institution: it is a field of an
    articulation, not a projection row.
    """
    # ASSIST publishes these unevenly ("C1000 " padded, "c1001" lowercase).
    # Normalize once, here, so the stored parts and the derived code agree.
    prefix = _normalize_part(raw.get("prefix"))
    number = _normalize_part(raw.get("courseNumber"))
    fields: dict[str, object] = {
        "course_code": _course_code(prefix, number),
        "prefix": prefix,
        "number": number,
        "title": raw.get("courseTitle"),
        "units_min": raw.get("minUnits"),
        "units_max": raw.get("maxUnits"),
    }
    if institution_id is not None:
        fields["institution_id"] = institution_id
    try:
        return model.model_validate(fields)
    except ValidationError as error:
        raise _fail(
            f"ASSIST course {prefix!r} {number!r} failed {model.__name__} validation: "
            f"{_validation_detail(error)}",
            AssistBuildCode.COURSE_CODE_UNPARSEABLE,
        ) from error


def _normalize_part(value: object) -> object:
    """Apply `normalize_course_code`'s own hygiene to a single part.

    The derived code is uppercased and whitespace-collapsed, but the stored
    `prefix`/`number` fields kept whatever ASSIST published, so a padded
    `"C1000 "` or a lowercase `"c1001"` failed its contract pattern while the
    code derived from it validated fine. Both sides now see the same string.

    Non-strings pass through so the contract reports the real type error rather
    than a confusing one about a value this helper invented.
    """
    return " ".join(value.upper().split()) if isinstance(value, str) else value


def _course_code(prefix: object, number: object) -> str:
    if not isinstance(prefix, str) or not isinstance(number, str):
        raise _fail(
            f"ASSIST course carried prefix {type(prefix).__name__} and number "
            f"{type(number).__name__}, expected two strings",
            AssistBuildCode.COURSE_CODE_UNPARSEABLE,
        )
    try:
        return course_code_from_parts(prefix, number)
    except ValueError as error:
        raise _fail(
            f"ASSIST course code {prefix!r} {number!r} did not normalize",
            AssistBuildCode.COURSE_CODE_UNPARSEABLE,
        ) from error


def dedupe_course_rows[ProjectionRow: (CcCourse, TargetCourse)](
    rows: Iterable[ProjectionRow],
) -> tuple[list[ProjectionRow], int]:
    """The vocabulary gate's dedup: first occurrence wins, conflicts counted.

    One key is one row, so the projection the UI autocompletes over and the
    projection the transcript validator resolves against cannot disagree. A
    later row that differs from the kept one is a `course_projection_conflict`
    in the build report; a later identical row is just a repeat. Feed rows in
    sorted `assist_key` order and "first wins" is deterministic.
    """
    kept: dict[tuple[int, str], ProjectionRow] = {}
    conflicts = 0
    for row in rows:
        key = (row.institution_id, row.course_code)
        existing = kept.get(key)
        if existing is None:
            kept[key] = row
        elif existing != row:
            conflicts += 1
    return [kept[key] for key in sorted(kept)], conflicts


def normalize_institutions(raw: object) -> tuple[list[Institution], int]:
    """Every `/api/institutions` entry, sorted by id, with the unknown-kind count."""
    institutions: list[Institution] = []
    unknown = 0
    for entry in _as_list(raw, what="institutions", code=AssistBuildCode.ENVELOPE_INVALID):
        institution = normalize_institution(entry)
        if institution is None:
            unknown += 1
        else:
            institutions.append(institution)
    return sorted(institutions, key=lambda item: item.assist_id), unknown
