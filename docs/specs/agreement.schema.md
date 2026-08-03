# agreement

Canonical module: `backend/src/starmap/contracts/agreement.py`.

One published ASSIST articulation agreement between a sending community college and a receiving UC or CSU, for one academic year.
`Agreement` is the envelope; the `Articulation` rows that belong to it point back through `agreement_id`.

The module also holds the template-asset models (`TemplateCell`, `TemplateSection`, `RequirementGroupAsset`), which describe how a MAJOR agreement lays its receiving courses out into requirement groups.
Department agreements have no template (`templateAssets` is null in the department capture), so those models are absent for them rather than empty.

Field values are transcribed from the envelopes of `agreement_major_cse_cs_113_to_7_y76.json` and `agreement_dept_math_113_to_7_y76.json` plus their entries in the captured agreement-report lists.
This contract holds the NORMALIZED envelope; the double-decode and the template flattening are locked in `docs/implementation-plans/articulation/02-assist-fetch-normalize-store.md`.

## Agreement

| Field | Type | Constraints |
| --- | --- | --- |
| `agreement_id` | str | Pattern `^agr_[0-9a-f]{16}$`. |
| `assist_key` | str | Pattern `^[0-9]+/[0-9]+/to/[0-9]+/(Major\|Department)/.+$`. |
| `category` | `Literal["major", "dept"]` | Closed for v1. |
| `sending_institution_id` | int | `gt=0`. |
| `receiving_institution_id` | int | `gt=0`. |
| `academic_year_id` | int | `gt=0`. |
| `academic_year_label` | str | Pattern `^[0-9]{4}-[0-9]{4}$` plus the consecutive-years validator. |
| `label` | str | 1..300 chars; control-character hygiene. |
| `publish_date` | str | 1..40 chars; control-character hygiene. |

`assist_key` is the agreement's identity as ASSIST states it, in the two observed key formats: `76/113/to/7/Major/d2dfb7a8-...` (GUID tail) and `76/113/to/7/Department/8952` (integer tail).
The report lists also contain `SendingDepartment` keys (`76/113/to/7/SendingDepartment/9040`, owned by the sending institution); those are the mirror-direction agreements and are out of scope for v1, so the pattern excludes them and the fetcher never requests them.
That last clause became true only in S9c: `corridor.select_depts` now enforces it, and before that the walk fetched all 86 of the demo pair's dept reports and the 36 mirrors surfaced as `envelope_invalid` exclusions in the build report.
The exclusion is safe, and this was verified against the S9c capture rather than assumed: the 36 mirror agreements publish 120 articulation pairs, every one of which the 50 receiving-side agreements also publish, and those publish 329 further pairs the mirrors do not.
Widening `category` and this pattern later is an append, not a break.

`publish_date` is a VERBATIM provenance string, deliberately not a `datetime`.
ASSIST emits seven fractional-second digits (`2026-06-08T23:04:32.5510019`), which exceeds `datetime` microsecond precision; parsing would silently truncate a value we only ever display and compare for equality.
Nothing computes on it.

`label` is the report label from the agreements-list endpoint (`Mathematics/Computer Science B.S.`, `Mathematics`), which is what a student recognizes; the payload's own `name` field carries the same text.

## Agreement validators

| Validator | Rule |
| --- | --- |
| id derivation | `agreement_id == "agr_" + sha256_hex(assist_key)[:16]`; the error quotes both values. |
| distinct institutions | `sending_institution_id != receiving_institution_id`; the error quotes the value. |
| key/category coherence | The key's fifth segment is `Major` iff `category == "major"` and `Department` iff `category == "dept"`; the error quotes both. |
| key/id coherence | The key's leading three integers equal `academic_year_id`, `sending_institution_id`, `receiving_institution_id` in that order; the error quotes the key and the mismatching field. |
| consecutive year label | The second year in `academic_year_label` equals the first plus one; the error quotes the label. The rule is the module-level `check_consecutive_years`, which `evaluation.Citation.year_label` also calls so a citation and the agreement it cites cannot disagree about what a year label means. |

The id derivation is the house content-derived-id pattern (`sha256_hex` from `common/ids.py`): the id is a function of the key, so two builds of the same agreement cannot produce two ids, and an id cannot be reassigned to a different agreement.

The two key-coherence validators exist because the key is the citation every finding carries.
If the key and the structured fields could disagree, a finding could cite one agreement while having been evaluated against another, which the citation axiom forbids.

## Template assets

Major agreements only.
The normalizer flattens each ASSIST `RequirementGroup` asset into these models: rows collapse into their section's cell list, a null `instruction` becomes `And`, a `Conjunction` instruction supplies its own value, and `GeneralTitle`/`GeneralText` assets are dropped as prose.
The contract holds only that normalized result; it never sees a row or an instruction object.

### TemplateCell

| Field | Type | Constraints |
| --- | --- | --- |
| `cell_id` | str | GUID pattern `^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$`. |
| `course` | ReceivingCourse | Imported from `contracts/articulation.py`. |

`cell_id` is the join key to `Articulation.template_cell_id`.
A cell with no articulation carrying its id means "no articulation published for this cell": CSE 15L and CSE 29 in the major capture are exactly that, and they must render as unmet rather than vanish.

### TemplateSection

| Field | Type | Constraints |
| --- | --- | --- |
| `position` | int | `ge=0`. |
| `cells` | list[TemplateCell] | Min length 1. |

`TemplateCell` gained a `series` field in S9d, mirroring `Articulation`: `course` and `series` are both `ReceivingCourse | None` / `ReceivingSeries | None` with a model validator requiring exactly one, because a row that named both, or neither, could not be rendered.
`Requirement`, `GeneralEducation` and `CALGETC` row cells remain unmodeled and still exclude their whole group, since a row this build cannot render would otherwise silently shrink the requirement a student is shown.

### RequirementGroupAsset

| Field | Type | Constraints |
| --- | --- | --- |
| `group_id` | str | Same GUID pattern as `TemplateCell.cell_id`. |
| `position` | int | `ge=0`. |
| `conjunction` | `Literal["And", "Or"]` | The group's own conjunction, normalized from `instruction`. |
| `select_courses` | `int \| None` | Default `None`; when set, `ge=1` and `conjunction` must be `Or`. |
| `sections` | list[TemplateSection] | Min length 1. |
| `advisements` | list[str] | Default empty; each entry 1..2000 chars with control-character hygiene. |

`conjunction` is `Or` when the group offers a choice between sections (the CSE 15L / CSE 29 group in the major capture, whose `instruction` is `{"type": "Conjunction", "conjunction": "Or"}`) and `And` when every section is required.

`select_courses` is the N-from node, added in S9d as `select_at_least` and RENAMED with corrected semantics in S9e after verification against rendered agreements.
`None` means the `conjunction` alone decides: `And` requires every section in full, `Or` requires one section in full.
An integer means "complete at least this many COURSES, drawn from all of the group's sections as one pool"; a satisfied series cell counts as one toward the amount, because ASSIST's renderer treats the row as the countable unit.

The unit is courses, never sections, and that is measured rather than assumed.
ASSIST renders every N-from instruction as "Complete [at least] {amount} {amountUnitType} from {section letters joined by the instruction's own conjunction}": "Complete 1 course from A, B, or C" (UCLA MIMG B.S. group 1, three sections of three to four courses each), "Complete at least 1 course from A" (UCLA Human Biology B.S. group 2, one section of three courses), "Complete 1 sequence from A or B", "Complete 1 series from A, B, or C".
The S9d reading, "complete at least this many of the sections", inverted a pick-1-of-N into a complete-all-N for every multi-cell section; S9e measured 23,016 of 26,121 stored select groups diverging that way before the fix.
The rename forces every consumer to notice the semantics change; no consumer of `select_at_least` ever shipped.

It is paired with `conjunction = "Or"` and a model validator enforces that, because the pool is one disjunctive choice set.
The one instruction where ASSIST's own conjunction is semantically live, `NFromConjunction` with `conjunction: "And"` over MORE than one section (rendered "Complete 1 course from A and B"), is ambiguous between "from each" and "from the union" and is excluded rather than guessed; over a single section the conjunction names nothing (rendered "from A") and the union reading is exact.
`NFromArea` and `NFromFollowing` publish no conjunction at all and render "from the following", so the union reading is the only one available.

Only the unambiguous slice of ASSIST's selection rules maps here: `amountUnitType == "Course"` with `amountQuantifier` of `None` or `AtLeast`, `toAmountDeterminer` of `None`, and an area conjunction that is `Or`, absent, or inert.
Everything else remains a `template_shape_unsupported` exclusion, deliberately:

- `UpTo` is a CAP ("complete up to 8.00 semester units"), not a requirement; storing it as one would invert its meaning and tell a student they owe an elective ceiling.
- Unit-denominated amounts (`Unit`, `SemesterUnit`) count units rather than courses, and this contract has no unit arithmetic.
- `Series`, `Sequence`, `CourseOrCombination` and `OrMoreCourses` denominate the amount in objects the pool does not count.
- `toAmountDeterminer` of `Any` or `Each` adds a second quantifier over a range.
- `NFromConjunction` with a live `And` area conjunction is the ambiguity above.
`advisements` runs through the same pinned `advisement_texts` gate as `Articulation.advisements`.
Seven template-side lists feed it as of S9e, in deterministic payload order: the group's `advisements` and `attributes`, each section's `advisements` and `attributes`, each row's `attributes`, and each cell's `attributes`, `courseAttributes`, and `seriesAttributes`.
The cell `courseAttributes` list is the volume carrier (41,246 corridor entries, "Minimum grade required: B or better"); before S9e it was read by nothing, a silent drop the axiom forbids.
Cell `requirementAttributes` sits only on `Requirement` cells, which already exclude their group, and `receivingAttributes` is a verbatim mirror of the articulation-level lists; both are named here as examined rather than missed.

## Fixtures

Valid, transcribed from the captures:

| Fixture | Source |
| --- | --- |
| `agreement/major_cse_cs.json` | Key `76/113/to/7/Major/d2dfb7a8-d505-4e70-f33c-08ddd3b241a4`, label `Mathematics/Computer Science B.S.`, publish date `2026-06-08T23:04:32.5510019`. |
| `agreement/dept_math.json` | Key `76/113/to/7/Department/8952`, label `Mathematics`, publish date `2026-06-08T23:17:32.4509041`. |
| `requirement_group_asset/math_requirements.json` | Major capture asset at position 0: one section, six cells (MATH 18, 20A, 20B, 20C, 20D, 20E), `And`. |
| `requirement_group_asset/cse15l_or_cse29.json` | Major capture asset at position 3: two single-cell sections, `Or`. |
| `requirement_group_asset/select_one_of_two.json` | Hand-built from the S9d corridor shape: one two-cell section, `Or` with `select_courses = 1` ("Complete 1 course from A"). |

The template-asset fixtures live in their own directory because `RequirementGroupAsset` is not reachable through an `Agreement` payload (the envelope holds no template field), so the fixture harness cannot validate them with the `Agreement` model.

Invalid, under `agreement/`: `bad_id_derivation`, `bad_key_pattern`, `category_key_mismatch`, `same_institutions`, `key_ids_mismatch`, `bad_year_label`, `nonconsecutive_year_label`, `label_control_char`, `publish_date_empty`.
Invalid, under `requirement_group_asset/`: `template_cell_bad_guid`, `requirement_group_empty_sections`, `bad_group_conjunction`, `section_no_cells`, `negative_position`, `advisement_control_char`, `select_courses_with_and`, `select_courses_zero`.
The names beyond doc 01's locked list cover constraint families that would otherwise have no fixture proving they fire, which the increment's exit criteria forbid.
