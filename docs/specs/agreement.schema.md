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
| consecutive year label | The second year in `academic_year_label` equals the first plus one; the error quotes the label. |

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

### RequirementGroupAsset

| Field | Type | Constraints |
| --- | --- | --- |
| `group_id` | str | Same GUID pattern as `TemplateCell.cell_id`. |
| `position` | int | `ge=0`. |
| `conjunction` | `Literal["And", "Or"]` | The group's own conjunction, normalized from `instruction`. |
| `sections` | list[TemplateSection] | Min length 1. |
| `advisements` | list[str] | Default empty; each entry 1..2000 chars with control-character hygiene. |

`conjunction` is `Or` when the group offers a choice between sections (the CSE 15L / CSE 29 group in the major capture, whose `instruction` is `{"type": "Conjunction", "conjunction": "Or"}`) and `And` when every section is required.
`advisements` runs through the same fixture-pending `advisement_texts` gate as `Articulation.advisements`; every captured `attributes` and `advisements` list is empty today.

## Fixtures

Valid, transcribed from the captures:

| Fixture | Source |
| --- | --- |
| `agreement/major_cse_cs.json` | Key `76/113/to/7/Major/d2dfb7a8-d505-4e70-f33c-08ddd3b241a4`, label `Mathematics/Computer Science B.S.`, publish date `2026-06-08T23:04:32.5510019`. |
| `agreement/dept_math.json` | Key `76/113/to/7/Department/8952`, label `Mathematics`, publish date `2026-06-08T23:17:32.4509041`. |
| `requirement_group_asset/math_requirements.json` | Major capture asset at position 0: one section, six cells (MATH 18, 20A, 20B, 20C, 20D, 20E), `And`. |
| `requirement_group_asset/cse15l_or_cse29.json` | Major capture asset at position 3: two single-cell sections, `Or`. |

The template-asset fixtures live in their own directory because `RequirementGroupAsset` is not reachable through an `Agreement` payload (the envelope holds no template field), so the fixture harness cannot validate them with the `Agreement` model.

Invalid, under `agreement/`: `bad_id_derivation`, `bad_key_pattern`, `category_key_mismatch`, `same_institutions`, `key_ids_mismatch`, `bad_year_label`, `nonconsecutive_year_label`, `label_control_char`, `publish_date_empty`.
Invalid, under `requirement_group_asset/`: `template_cell_bad_guid`, `requirement_group_empty_sections`, `bad_group_conjunction`, `section_no_cells`, `negative_position`, `advisement_control_char`.
The names beyond doc 01's locked list cover constraint families that would otherwise have no fixture proving they fire, which the increment's exit criteria forbid.
