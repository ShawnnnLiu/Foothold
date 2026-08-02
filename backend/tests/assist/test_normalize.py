"""Normalization against the captured ASSIST payloads.

The two agreement fixtures are the only payload source, and they are never
edited: the poisoned cases below deep-copy a fixture and mutate the copy, so
what is on disk stays exactly what ASSIST served on 2026-07-31.

The assertions pin real payload facts (MATH 20D's honors-or-regular pair, the
MATH 1C + 1D series behind MATH 20E, the CSE 15L / CSE 29 `Or` group, the
"No Course Articulated" rows on MATH 10B/10C) rather than restating the
algorithm, so a mapping change that silently altered a transfer rule fails
here.
"""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from starmap.assist.errors import AssistNormalizeError
from starmap.assist.normalize import (
    Exclusion,
    advisement_texts,
    decode_envelope,
    decode_field,
    dedupe_course_rows,
    normalize_academic_years,
    normalize_agreement,
    normalize_institution,
    normalize_institutions,
)
from starmap.contracts.agreement import AgreementCategory
from starmap.contracts.articulation_expr import AllOf, AnyOf, CourseLeaf
from starmap.contracts.reason_codes import AssistBuildCode

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "assist"
MAJOR = "agreement_major_cse_cs_113_to_7_y76.json"
DEPT = "agreement_dept_math_113_to_7_y76.json"
# The S9c capture that pins the populated advisement shape (College of Marin
# -> San Jose State, Computer Science B.S.), which the spike captures could not.
ADVISEMENTS = "agreement_with_advisements_4_to_39_y76.json"
MAJOR_KEY = "76/113/to/7/Major/f8d5b3e6-1d24-4b7a-9a3f-1b2c3d4e5f60"
DEPT_KEY = "76/113/to/7/Department/12"
DE_ANZA = 113
UCSD = 7


def fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def normalize(raw: Any, *, key: str, category: AgreementCategory, label: str) -> Any:
    return normalize_agreement(
        raw,
        assist_key=key,
        category=category,
        label=label,
        sending_id=DE_ANZA,
        receiving_id=UCSD,
    )


def major() -> Any:
    return normalize(
        fixture(MAJOR),
        key=MAJOR_KEY,
        category="major",
        label="Mathematics/Computer Science B.S.",
    )


def dept() -> Any:
    return normalize(fixture(DEPT), key=DEPT_KEY, category="dept", label="Mathematics")


def articulation_for(normalized: Any, course_code: str) -> Any:
    (found,) = [
        item
        for item in normalized.articulations
        if item.receiving_course.course_code == course_code
    ]
    return found


def poisoned_dept(mutate: Any) -> Any:
    """A deep copy of the dept fixture with its articulation list rewritten."""
    raw = fixture(DEPT)
    entries = deepcopy(json.loads(raw["result"]["articulations"]))
    mutate(entries)
    raw["result"]["articulations"] = json.dumps(entries)
    return raw


# --- the two captured agreements, end to end --------------------------------


def test_major_agreement_normalizes_into_its_contract() -> None:
    normalized = major()
    assert normalized.agreement.agreement_id.startswith("agr_")
    assert normalized.agreement.academic_year_id == 76
    assert normalized.agreement.academic_year_label == "2025-2026"
    assert normalized.agreement.category == "major"
    assert len(normalized.articulations) == 8
    assert normalized.exclusions == ()


def test_major_articulation_positions_are_the_payload_indexes() -> None:
    positions = [item.position for item in major().articulations]
    assert positions == list(range(8))


def test_every_major_articulation_carries_its_template_cell_id() -> None:
    """The join key to `TemplateCell.cell_id`; without it a finding cannot say
    which requirement cell it satisfied."""
    assert all(item.template_cell_id is not None for item in major().articulations)


def test_math20d_maps_to_any_of_two_single_course_groups() -> None:
    """Two groups of one course each, joined by the payload's single `Or`:
    De Anza MATH 2A or its honors twin MATH 2AH."""
    expr = articulation_for(major(), "MATH 20D").sending_expr
    assert expr == AnyOf(any=[CourseLeaf(course="MATH 2A"), CourseLeaf(course="MATH 2AH")])


def test_math20e_maps_to_an_all_of_the_two_course_series() -> None:
    """One group, `courseConjunction: And`: the half-series case the evaluator
    later reports as `partial_series`."""
    expr = articulation_for(major(), "MATH 20E").sending_expr
    assert expr == AllOf(all=[CourseLeaf(course="MATH 1C"), CourseLeaf(course="MATH 1D")])


def test_math20c_nests_two_series_under_one_or() -> None:
    """The deepest observed shape, and exactly `MAX_DEPTH`."""
    expr = articulation_for(major(), "MATH 20C").sending_expr
    assert expr == AnyOf(
        any=[
            AllOf(all=[CourseLeaf(course="MATH 1C"), CourseLeaf(course="MATH 1D")]),
            AllOf(all=[CourseLeaf(course="MATH 1CH"), CourseLeaf(course="MATH 1DH")]),
        ]
    )


def test_major_template_assets_become_four_requirement_groups() -> None:
    groups = major().requirement_groups
    assert [group.position for group in groups] == [0, 1, 2, 3]
    assert [group.conjunction for group in groups] == ["And", "And", "And", "Or"]


def test_the_or_group_holds_the_cse15l_and_cse29_cells_in_two_sections() -> None:
    """The `Or`-instruction group whose cells no articulation points at: it must
    survive normalization so the UI can render it as unmet."""
    group = major().requirement_groups[3]
    assert group.conjunction == "Or"
    assert [[cell.course.course_code for cell in section.cells] for section in group.sections] == [
        ["CSE 15L"],
        ["CSE 29"],
    ]


def test_general_text_and_title_assets_are_dropped() -> None:
    """Three of the seven assets are prose, not requirements (doc 02, v1)."""
    assets = json.loads(fixture(MAJOR)["result"]["templateAssets"])
    assert len(assets) == 7
    assert len(major().requirement_groups) == 4


def test_dept_agreement_normalizes_into_bare_articulations() -> None:
    normalized = dept()
    assert len(normalized.articulations) == 11
    assert normalized.requirement_groups == ()
    assert normalized.exclusions == ()
    assert all(item.template_cell_id is None for item in normalized.articulations)


def test_dept_no_course_articulated_rows_carry_no_sending_expression() -> None:
    """MATH 10B and 10C: `sendingArticulation: null` is "No Course Articulated",
    which is a fact about the agreement, not a parse failure."""
    empty = {
        item.receiving_course.course_code
        for item in dept().articulations
        if item.sending_expr is None
    }
    assert empty == {"MATH 10B", "MATH 10C"}


def test_dept_single_course_group_maps_to_a_bare_leaf() -> None:
    assert articulation_for(dept(), "MATH 10A").sending_expr == CourseLeaf(course="MATH 12")


def test_padded_course_parts_are_collapsed_before_they_reach_a_contract() -> None:
    """ASSIST pads its split parts (`courseNumber: "C1000 "`).

    The code was derived from the COLLAPSED pair while the stored fields kept
    the raw one, so a padded value failed `COURSE_NUMBER_PATTERN` even though
    its own course code validated: 42 corridor articulations were excluded by
    that mismatch rather than by anything wrong in the payload.
    """

    def mutate(entries: list[Any]) -> None:
        course = entries[0]["sendingArticulation"]["items"][0]["items"][0]
        course["prefix"] = "  MATH  "
        course["courseNumber"] = "12 "

    normalized = normalize(
        poisoned_dept(mutate), key=DEPT_KEY, category="dept", label="Mathematics"
    )

    assert normalized.exclusions == ()
    (course,) = [row for row in normalized.cc_courses if row.course_code == "MATH 12"]
    assert (course.prefix, course.number) == ("MATH", "12")


def test_projections_come_from_both_sides_of_every_articulation() -> None:
    normalized = dept()
    cc_courses, _ = dedupe_course_rows(normalized.cc_courses)
    target_courses, _ = dedupe_course_rows(normalized.target_courses)
    assert all(course.institution_id == DE_ANZA for course in cc_courses)
    assert all(course.institution_id == UCSD for course in target_courses)
    assert "STAT C1000H" in {course.course_code for course in cc_courses}
    assert {course.course_code for course in target_courses} >= {"MATH 10B", "MATH 20E"}


def test_template_cell_courses_also_project_as_target_courses() -> None:
    """CSE 15L and CSE 29 have no articulation, so only the template reaches
    them; the target vocabulary must still contain them."""
    codes = {course.course_code for course in major().target_courses}
    assert {"CSE 15L", "CSE 29"} <= codes


# --- fault isolation --------------------------------------------------------


def test_three_poisoned_articulations_produce_three_exclusions_and_keep_the_rest() -> None:
    """One poisoned member never breaks the build (testing strategy seam)."""

    def mutate(entries: list[Any]) -> None:
        entries[0]["type"] = "Series"
        entries[3]["course"]["courseNumber"] = "not a number"
        # A structured N-from rule where prose belongs: still unmodeled, so
        # still an exclusion rather than an invented advisement.
        entries[4]["attributes"] = [{"type": "NFollowing", "amount": 2.0, "position": 0}]

    normalized = normalize(
        poisoned_dept(mutate), key=DEPT_KEY, category="dept", label="Mathematics"
    )
    assert len(normalized.articulations) == 8
    assert [item.position for item in normalized.exclusions] == [0, 3, 4]
    assert [item.reason_code for item in normalized.exclusions] == [
        AssistBuildCode.ARTICULATION_TYPE_UNSUPPORTED,
        AssistBuildCode.COURSE_CODE_UNPARSEABLE,
        AssistBuildCode.ADVISEMENT_SHAPE_UNKNOWN,
    ]
    assert all(item.assist_key == DEPT_KEY for item in normalized.exclusions)


def test_an_unsupported_sending_item_type_excludes_only_its_articulation() -> None:
    def mutate(entries: list[Any]) -> None:
        entries[0]["sendingArticulation"]["items"][0]["items"][0]["type"] = "Series"

    normalized = normalize(
        poisoned_dept(mutate), key=DEPT_KEY, category="dept", label="Mathematics"
    )
    assert len(normalized.articulations) == 10
    assert [item.reason_code for item in normalized.exclusions] == [
        AssistBuildCode.ARTICULATION_TYPE_UNSUPPORTED
    ]


def test_mixed_group_conjunctions_are_excluded_rather_than_guessed() -> None:
    """Only `Or` is observed; a mixed set cannot be one node, so it is a typed
    exclusion instead of a chosen winner."""

    def mutate(entries: list[Any]) -> None:
        conjunctions = entries[3]["sendingArticulation"]["courseGroupConjunctions"]
        conjunctions.append({**conjunctions[0], "groupConjunction": "And"})

    normalized = normalize(
        poisoned_dept(mutate), key=DEPT_KEY, category="dept", label="Mathematics"
    )
    assert [item.reason_code for item in normalized.exclusions] == [
        AssistBuildCode.MIXED_GROUP_CONJUNCTION
    ]


def test_a_multi_group_rule_with_no_conjunctions_is_excluded() -> None:
    """An empty conjunction list does not say how to join two groups; guessing
    would silently invent a transfer rule."""

    def mutate(entries: list[Any]) -> None:
        entries[3]["sendingArticulation"]["courseGroupConjunctions"] = []

    normalized = normalize(
        poisoned_dept(mutate), key=DEPT_KEY, category="dept", label="Mathematics"
    )
    assert [item.reason_code for item in normalized.exclusions] == [
        AssistBuildCode.MIXED_GROUP_CONJUNCTION
    ]


def test_an_unmodeled_template_group_is_excluded_and_the_agreement_still_stores() -> None:
    raw = fixture(MAJOR)
    assets = json.loads(raw["result"]["templateAssets"])
    groups = [asset for asset in assets if asset["type"] == "RequirementGroup"]
    groups[1]["instruction"] = {"type": "Selection", "selectionType": "Select"}
    raw["result"]["templateAssets"] = json.dumps(assets)

    normalized = normalize(raw, key=MAJOR_KEY, category="major", label="Mathematics")
    assert len(normalized.requirement_groups) == 3
    assert len(normalized.articulations) == 8
    assert [item.reason_code for item in normalized.exclusions] == [
        AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED
    ]
    assert normalized.exclusions[0].position == 1


def test_a_template_row_without_exactly_one_course_cell_is_excluded() -> None:
    raw = fixture(MAJOR)
    assets = json.loads(raw["result"]["templateAssets"])
    groups = [asset for asset in assets if asset["type"] == "RequirementGroup"]
    groups[2]["sections"][0]["rows"][0]["cells"] = []
    raw["result"]["templateAssets"] = json.dumps(assets)

    normalized = normalize(raw, key=MAJOR_KEY, category="major", label="Mathematics")
    assert len(normalized.requirement_groups) == 3
    assert [item.reason_code for item in normalized.exclusions] == [
        AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED
    ]


# --- the envelope -----------------------------------------------------------


def test_an_unsuccessful_envelope_is_typed() -> None:
    raw = fixture(DEPT)
    raw["isSuccessful"] = False
    with pytest.raises(AssistNormalizeError) as caught:
        decode_envelope(raw)
    assert caught.value.assist_reason_code is AssistBuildCode.ENVELOPE_INVALID


def test_a_missing_result_is_typed() -> None:
    with pytest.raises(AssistNormalizeError) as caught:
        decode_envelope({"isSuccessful": True, "result": None})
    assert caught.value.assist_reason_code is AssistBuildCode.ENVELOPE_INVALID


def test_a_corrupt_stringified_field_names_the_field() -> None:
    result = decode_envelope(fixture(DEPT))
    result["articulations"] = "{not json"
    with pytest.raises(AssistNormalizeError) as caught:
        decode_field(result, "articulations")
    assert caught.value.assist_reason_code is AssistBuildCode.FIELD_DECODE_FAILED
    assert "articulations" in caught.value.message


def test_a_null_stringified_field_decodes_to_none() -> None:
    """Dept agreements carry `templateAssets: null`, which is absence, not
    corruption."""
    assert decode_field(decode_envelope(fixture(DEPT)), "templateAssets") is None


def test_a_broken_envelope_excludes_the_whole_agreement() -> None:
    raw = fixture(DEPT)
    raw["isSuccessful"] = False
    with pytest.raises(AssistNormalizeError) as caught:
        normalize(raw, key=DEPT_KEY, category="dept", label="Mathematics")
    assert caught.value.assist_reason_code is AssistBuildCode.ENVELOPE_INVALID


# --- advisements ------------------------------------------------------------


@pytest.mark.parametrize("attributes", [None, []])
def test_absent_and_empty_attributes_both_mean_no_advisements(attributes: object) -> None:
    """ASSIST sends `null` on "No Course Articulated" rows and `[]` elsewhere."""
    assert advisement_texts(attributes) == []


def test_the_pinned_shape_maps_to_text_in_published_order() -> None:
    """`{content, position}` is the shape S9c measured live; `position` is the
    published order, so the result cannot depend on list order."""
    attributes = [
        {"content": "second", "position": 1},
        {"content": "  first  ", "position": 0},
    ]

    assert advisement_texts(attributes) == ["first", "second"]


@pytest.mark.parametrize(
    "attributes",
    [
        pytest.param("text", id="not-a-list"),
        pytest.param({"a": 1}, id="a-mapping"),
        pytest.param([{"position": 0}], id="no-content"),
        pytest.param([{"content": 7, "position": 0}], id="content-not-a-string"),
        pytest.param([{"content": "   ", "position": 0}], id="content-empty-after-strip"),
        pytest.param([{"content": "x" * 2001, "position": 0}], id="content-too-long"),
        pytest.param([{"content": "line\x07break", "position": 0}], id="control-characters"),
    ],
)
def test_anything_but_the_pinned_shape_is_still_the_typed_exclusion(attributes: object) -> None:
    """The gate narrowed in S9c; it did not disappear. Nothing invents,
    paraphrases, truncates, or silently drops an advisement."""
    with pytest.raises(AssistNormalizeError) as caught:
        advisement_texts(attributes)
    assert caught.value.assist_reason_code is AssistBuildCode.ADVISEMENT_SHAPE_UNKNOWN


def test_the_structured_n_from_shape_is_excluded_rather_than_flattened() -> None:
    """Template sections carry `{"type": "NFollowing", "amount": 2.0, ...}` in
    the same field name: a requirement rule, not prose. Flattening it to text
    would invent an advisement, and skipping it would let a group that means
    "select 2 of" read as "complete all of".
    """
    selection = [
        {
            "type": "NFollowing",
            "amount": 2.0,
            "amountUnitType": "Course",
            "position": 0,
            "selectionType": "Select",
        }
    ]

    with pytest.raises(AssistNormalizeError) as caught:
        advisement_texts(selection)
    assert caught.value.assist_reason_code is AssistBuildCode.ADVISEMENT_SHAPE_UNKNOWN


@pytest.mark.parametrize(
    "level",
    ["articulation", "courseAttributes", "sending_articulation", "group", "course"],
)
def test_every_articulation_level_advisement_reaches_the_contract(level: str) -> None:
    """Seven levels feed `advisement_texts`; these five sit on an articulation.

    `courseAttributes` is in the list because the S9c sweep found real prose
    there ("Articulation is subject to placement by proficiency exam") that
    nothing was reading at all.
    """
    content = [{"content": "Complete with a grade of C or better.", "position": 0}]

    def mutate(entries: list[Any]) -> None:
        entry = entries[0]
        sending = entry["sendingArticulation"]
        if level == "courseAttributes":
            entry["courseAttributes"] = content
            return
        targets = {
            "articulation": entry,
            "sending_articulation": sending,
            "group": sending["items"][0],
            "course": sending["items"][0]["items"][0],
        }
        targets[level]["attributes"] = content

    normalized = normalize(
        poisoned_dept(mutate), key=DEPT_KEY, category="dept", label="Mathematics"
    )

    assert normalized.exclusions == ()
    assert len(normalized.articulations) == 11
    text = "Complete with a grade of C or better."
    first = normalized.articulations[0]
    if level in {"articulation", "courseAttributes", "sending_articulation"}:
        assert first.advisements == [text]
    else:
        # Group and course texts become note leaves INSIDE the group node, so
        # no advisement can be satisfied by taking the course.
        assert text in json.dumps(first.sending_expr.model_dump())


def test_a_group_level_advisement_becomes_a_note_leaf_in_the_expression() -> None:
    """The note rides inside the group node rather than beside it: an `all` of
    the course and its note, never an `any` that the course alone satisfies."""

    def mutate(entries: list[Any]) -> None:
        entries[0]["sendingArticulation"]["items"][0]["attributes"] = [
            {"content": "Must be taken for a letter grade", "position": 0}
        ]

    normalized = normalize(
        poisoned_dept(mutate), key=DEPT_KEY, category="dept", label="Mathematics"
    )

    expression = normalized.articulations[0].sending_expr.model_dump()
    assert "all" in expression
    assert {"note": "Must be taken for a letter grade"} in expression["all"]


def test_a_template_group_advisement_is_carried_not_excluded() -> None:
    """ASSIST publishes group prose under `attributes`; before S9c measured
    that, nothing read the field and 46 corridor advisements vanished."""
    raw = fixture(MAJOR)
    assets = json.loads(raw["result"]["templateAssets"])
    groups = [asset for asset in assets if asset["type"] == "RequirementGroup"]
    groups[0]["attributes"] = [{"content": "Minimum grade required: C or better", "position": 0}]
    raw["result"]["templateAssets"] = json.dumps(assets)

    normalized = normalize(raw, key=MAJOR_KEY, category="major", label="Mathematics")

    assert normalized.exclusions == ()
    assert len(normalized.requirement_groups) == 4
    assert normalized.requirement_groups[0].advisements == ["Minimum grade required: C or better"]


def test_a_template_section_selection_rule_excludes_only_that_group() -> None:
    raw = fixture(MAJOR)
    assets = json.loads(raw["result"]["templateAssets"])
    groups = [asset for asset in assets if asset["type"] == "RequirementGroup"]
    groups[0]["sections"][0]["advisements"] = [
        {"type": "NFollowing", "amount": 1.0, "position": 0, "selectionType": "Select"}
    ]
    raw["result"]["templateAssets"] = json.dumps(assets)

    normalized = normalize(raw, key=MAJOR_KEY, category="major", label="Mathematics")

    assert len(normalized.requirement_groups) == 3
    assert len(normalized.articulations) == 8
    assert [item.reason_code for item in normalized.exclusions] == [
        AssistBuildCode.ADVISEMENT_SHAPE_UNKNOWN
    ]


def test_the_original_captures_carry_no_advisements() -> None:
    """The seven spike captures are all-empty at every level; the advisement
    fixture below is what pins the populated shape."""
    assert all(item.advisements == [] for item in major().articulations)
    assert all(group.advisements == [] for group in major().requirement_groups)


def test_the_captured_advisement_agreement_maps_its_real_texts() -> None:
    """The S9c capture: College of Marin -> San Jose State Computer Science,
    the payload the mapping was pinned from.

    Its four sending-course advisements land on two articulations as note
    leaves. Its one group-level advisement does NOT survive, because that group
    carries an `NFromArea` instruction and is excluded whole: the advisement
    goes with a typed exclusion in the report rather than into a group whose
    selection rule this build cannot express.
    """
    normalized = normalize_agreement(
        fixture(ADVISEMENTS),
        assist_key="76/4/to/39/Major/3ccc93fd-a5dc-4e22-3433-08ddb349963e",
        category="major",
        label="Computer Science, B.S.",
        sending_id=4,  # College of Marin
        receiving_id=39,  # San Jose State
    )

    note = "Complete entire sequence at same institution prior to transfer"
    with_notes = [
        item.position
        for item in normalized.articulations
        if item.sending_expr is not None and note in json.dumps(item.sending_expr.model_dump())
    ]
    assert with_notes == [3, 10]
    assert normalized.requirement_groups == ()
    assert {item.reason_code for item in normalized.exclusions} == {
        AssistBuildCode.TEMPLATE_SHAPE_UNSUPPORTED
    }


# --- institutions and years -------------------------------------------------


def test_institutions_map_to_their_corridor_kinds() -> None:
    entries = fixture("institutions.json")
    by_id = {entry["id"]: entry for entry in entries}
    assert normalize_institution(by_id[113]) is not None
    de_anza = normalize_institution(by_id[113])
    ucsd = normalize_institution(by_id[7])
    assert de_anza is not None and ucsd is not None
    assert (de_anza.code, de_anza.kind) == ("DAC", "cc")
    assert (ucsd.code, ucsd.kind) == ("UCSD", "uc")


def test_the_latest_name_wins_for_a_renamed_institution() -> None:
    """CSU Maritime is `California Maritime Academy` before 2015 and
    `California State University, Maritime Academy` after."""
    by_id = {entry["id"]: entry for entry in fixture("institutions.json")}
    csumaritime = normalize_institution(by_id[1])
    assert csumaritime is not None
    assert csumaritime.kind == "csu"
    assert csumaritime.name == "California State University, Maritime Academy"


def test_a_private_institution_is_counted_rather_than_stored() -> None:
    """Category 5 is outside a CCC -> UC/CSU corridor; None is a census, not a
    failure."""
    private = next(entry for entry in fixture("institutions.json") if entry["category"] == 5)
    assert normalize_institution(private) is None


def test_the_full_institution_list_splits_into_stored_and_unknown() -> None:
    institutions, unknown = normalize_institutions(fixture("institutions.json"))
    assert len(institutions) == 148
    assert unknown == 33
    assert [item.assist_id for item in institutions] == sorted(
        item.assist_id for item in institutions
    )


def test_academic_years_derive_their_label_from_the_fall_year() -> None:
    years = normalize_academic_years(fixture("academic_years.json"))
    latest = {year.year_id: year for year in years}[76]
    assert (latest.label, latest.fall_year) == ("2025-2026", 2025)
    assert [year.year_id for year in years] == sorted(year.year_id for year in years)


# --- the projection dedup gate ----------------------------------------------


def test_identical_repeat_rows_dedupe_without_a_conflict() -> None:
    """MATH 1C articulates to both MATH 20C and MATH 20E; one key is one row."""
    rows, conflicts = dedupe_course_rows(dept().cc_courses)
    codes = [row.course_code for row in rows]
    assert codes == sorted(set(codes))
    assert conflicts == 0


def test_a_differing_repeat_row_keeps_the_first_and_counts_a_conflict() -> None:
    rows = list(dept().cc_courses)
    first = rows[0]
    rows.append(first.model_copy(update={"title": "A different title"}))
    kept, conflicts = dedupe_course_rows(rows)
    assert conflicts == 1
    assert next(row for row in kept if row.course_code == first.course_code) == first


def test_exclusions_are_hashable_frozen_records() -> None:
    """The report folds them into JSON; a mutable record could drift between
    being counted and being printed."""
    exclusion = Exclusion(DEPT_KEY, 3, AssistBuildCode.COURSE_CODE_UNPARSEABLE, "detail")
    twin = Exclusion(DEPT_KEY, 3, AssistBuildCode.COURSE_CODE_UNPARSEABLE, "detail")
    assert len({exclusion, twin}) == 1
