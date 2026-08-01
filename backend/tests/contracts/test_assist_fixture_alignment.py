"""The increment's exit proof: the contracts fit the captured ASSIST payloads.

This asserts the payload facts the contracts were designed from, directly
against the untouched captures in `tests/fixtures/assist/`. It deliberately
does NOT duplicate the normalizer (increment 5 owns the decode-and-map
algorithm); it only pins the facts that would silently invalidate a contract
decision if ASSIST's shape turned out to be different from what the spike
recorded.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from starmap.contracts.codes import normalize_course_code

ASSIST_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "assist"

MAJOR = "agreement_major_cse_cs_113_to_7_y76.json"
DEPT = "agreement_dept_math_113_to_7_y76.json"


def load_result(name: str) -> dict[str, Any]:
    payload: dict[str, Any] = json.loads((ASSIST_DIR / name).read_text())["result"]
    return payload


def decode_articulations(name: str) -> list[dict[str, Any]]:
    """`articulations` is a JSON string inside a JSON document: decode twice."""
    decoded: list[dict[str, Any]] = json.loads(load_result(name)["articulations"])
    return decoded


def inner(entry: dict[str, Any]) -> dict[str, Any]:
    """Template-cell wrappers nest the articulation; base-model entries are it."""
    articulation: dict[str, Any] = entry["articulation"] if "templateCellId" in entry else entry
    return articulation


def sending_courses(articulation: dict[str, Any]) -> list[dict[str, Any]]:
    sending = articulation["sendingArticulation"]
    if sending is None:
        return []
    return [item for group in sending["items"] for item in group["items"]]


def test_captured_agreements_hold_the_expected_articulation_counts() -> None:
    assert len(decode_articulations(MAJOR)) == 8
    assert len(decode_articulations(DEPT)) == 11


@pytest.mark.parametrize("name", [MAJOR, DEPT])
def test_every_articulation_is_of_type_course(name: str) -> None:
    """`Articulation` models only `Course` rows; another type would need the
    `articulation_type_unsupported` exclusion, not a contract change."""
    assert {inner(entry)["type"] for entry in decode_articulations(name)} == {"Course"}


def test_major_entries_are_template_cell_wrappers_and_dept_entries_are_not() -> None:
    assert all("templateCellId" in entry for entry in decode_articulations(MAJOR))
    assert all("templateCellId" not in entry for entry in decode_articulations(DEPT))


def test_no_course_articulated_appears_as_a_null_sending_articulation() -> None:
    """MATH 10B and 10C are the capture's "No Course Articulated" rows, the
    encoding behind `Articulation.sending_expr = None`."""
    null_rows = {
        entry["course"]["courseNumber"]
        for entry in decode_articulations(DEPT)
        if entry["sendingArticulation"] is None
    }
    assert null_rows == {"10B", "10C"}


def test_math20d_is_two_groups_joined_by_one_or_conjunction() -> None:
    (entry,) = [
        entry
        for entry in decode_articulations(MAJOR)
        if inner(entry)["course"]["courseNumber"] == "20D"
    ]
    sending = inner(entry)["sendingArticulation"]
    assert len(sending["items"]) == 2
    assert [c["groupConjunction"] for c in sending["courseGroupConjunctions"]] == ["Or"]


def test_only_or_group_conjunctions_are_observed() -> None:
    """Doc 02 maps all-`Or` to `AnyOf` and all-`And` to `AllOf`; a mixed set is
    an exclusion. Only `Or` exists in the captures, so `AllOf` at the group-join
    level is currently untested by real data."""
    observed = {
        conjunction["groupConjunction"]
        for name in (MAJOR, DEPT)
        for entry in decode_articulations(name)
        if inner(entry)["sendingArticulation"] is not None
        for conjunction in inner(entry)["sendingArticulation"]["courseGroupConjunctions"]
    }
    assert observed == {"Or"}


@pytest.mark.parametrize("name", [MAJOR, DEPT])
def test_every_observed_course_code_normalizes(name: str) -> None:
    """Both sides of every articulation must survive `COURSE_CODE_RE`, or the
    build would exclude real rows as `course_code_unparseable`."""
    for entry in decode_articulations(name):
        articulation = inner(entry)
        for course in [articulation["course"], *sending_courses(articulation)]:
            code = f"{course['prefix']} {course['courseNumber']}"
            assert normalize_course_code(code) == code


def test_every_template_cell_course_code_normalizes() -> None:
    for asset in json.loads(load_result(MAJOR)["templateAssets"]):
        if asset["type"] != "RequirementGroup":
            continue
        for section in asset["sections"]:
            for row in section["rows"]:
                for cell in row["cells"]:
                    course = cell["course"]
                    code = f"{course['prefix']} {course['courseNumber']}"
                    assert normalize_course_code(code) == code


def test_template_cells_join_to_articulations_by_cell_id() -> None:
    """The join `TemplateCell.cell_id == Articulation.template_cell_id`, plus
    the two cells (CSE 15L, CSE 29) that no articulation points at."""
    cell_ids = {
        cell["id"]: cell["course"]["courseNumber"]
        for asset in json.loads(load_result(MAJOR)["templateAssets"])
        if asset["type"] == "RequirementGroup"
        for section in asset["sections"]
        for row in section["rows"]
        for cell in row["cells"]
    }
    articulated = {entry["templateCellId"] for entry in decode_articulations(MAJOR)}
    assert articulated <= set(cell_ids)
    assert {cell_ids[cell_id] for cell_id in set(cell_ids) - articulated} == {"15L", "29"}


def test_dept_agreements_carry_no_template_assets() -> None:
    assert load_result(DEPT)["templateAssets"] is None


@pytest.mark.parametrize("name", [MAJOR, DEPT])
def test_no_attributes_list_carries_content_at_any_of_the_four_levels(name: str) -> None:
    """The advisement fixture-pending precondition: `advisement_texts` may raise
    on any non-empty list precisely because none exists yet.

    REMOVE this test when split S9c lands an advisement-bearing fixture and
    pins the real shape.
    """
    for entry in decode_articulations(name):
        articulation = inner(entry)
        for key in ("attributes", "courseAttributes", "receivingAttributes"):
            assert not articulation[key]
        sending = articulation["sendingArticulation"]
        if sending is None:
            continue
        assert sending["attributes"] == []
        for group in sending["items"]:
            assert group["attributes"] == []
            for course in group["items"]:
                assert course["attributes"] == []


def test_articulation_level_attribute_lists_are_null_exactly_on_no_articulation_rows() -> None:
    """Payload fact the spike doc does not record, found by this test: on the
    two department rows with `sendingArticulation: null`, all three
    articulation-level attribute lists are `null` rather than `[]`.

    `advisement_texts` (doc 02) is specified over a list, so increment 5 must
    treat `null` as "no advisements" and not as an unknown shape; a bare
    truthiness check is not enough, since a future non-empty list must still
    raise `advisement_shape_unknown`.
    """
    null_rows = {
        entry["course"]["courseNumber"]
        for entry in decode_articulations(DEPT)
        if entry["attributes"] is None
    }
    assert null_rows == {"10B", "10C"}
    for entry in decode_articulations(DEPT):
        is_null_row = entry["course"]["courseNumber"] in null_rows
        assert (entry["sendingArticulation"] is None) is is_null_row
        for key in ("attributes", "courseAttributes", "receivingAttributes"):
            assert (entry[key] is None) is is_null_row
