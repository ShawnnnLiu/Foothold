# Increment F4: Mode B Arbitrage (Backend + Tab UI)

Goal: the deterministic arbitrage engine, its contract and endpoint, and the arbitrage tab, completing Mode B end to end with no LLM anywhere.
Binding references: `docs/FOOTHOLD_PATHFINDERS_PLAN.md:164-170` (Mode B definition and ranking formula), TR 4.5 (contract discipline: spec first, then model, fixtures, generated schema, tests), the prototype's `data-screen-label="Arbitrage"` section (layout truth), and the cost semantics in `transfer/costs.py`.

No new dependencies.
Contract discipline order is mandatory: `docs/specs/arbitrage.schema.md` first, then the model, fixtures, regenerated schemas, tests.

## Contract: `contracts/arbitrage.py` (locked shape)

```python
class ArbitrageRow(FROZEN):
    missing_course_codes: list[CourseCode]      # min 1, unique; the CC courses to take
    receiving_course_code: CourseCode | None    # None when the receiving side is a series
    receiving_course_title: str | None
    receiving_series_name: str | None           # exactly one of code/series populated
    units: float                                # > 0; receiving-side units
    savings_dollars: float | None               # None when the target has no per-unit rate
    citation: Citation                          # always present; Mode B never emits an uncited row
```

Spec doc, valid fixtures (one dollar row, one `None`-dollar row, one series row), invalid fixtures (empty `missing_course_codes`, both receiving fields set, negative units, missing citation), registry entry in `scripts/generate_schemas.py`, committed `backend/schemas/arbitrage.schema.json`.

## Engine: `transfer/arbitrage.py` (locked algorithm)

```python
build_arbitrage(evaluation: Evaluation, bundle: AgreementBundle, cost_table: CostTable | None)
    -> tuple[list[ArbitrageRow], int]   # (rows, omitted_no_rate_count)
```

1. Candidate set: every major-agreement articulation whose sending expression is NOT fully satisfied by the evaluation's resolved course set (recompute with `evaluate_expr`; do not parse findings text).
   This yields both flavors the prototype shows: untouched articulations (CIS 22A -> CSE 8A) and partial series completions (MATH 1D completing MATH 20E).
2. For each candidate: `missing_course_codes` = the expression's missing course leaves (from `ExprOutcome.missing`); skip candidates whose expression has no course leaves (note-only or no-articulation cells; nothing purchasable).
3. `units` = the receiving cell's units via the same `_cell_units` accounting the evaluator uses; receiving code/title/series from the articulation's receiving side.
4. `savings_dollars = round(units * (target_rate - cc_per_unit_default), 2)` with `target_rate = cost_table.target_rate(receiving_id)`; a `None` rate (or absent table) means `savings_dollars = None`, never zero.
5. Order: `savings_dollars` descending with `None` rows after all dollar rows, then articulation position ascending; the tuple's second element counts rows that would be silently unrankable, surfaced instead of dropped.
6. Pure function: no clock, no ids, no I/O.

## Route (in doc-01's `routes.py`)

`GET /api/arbitrage?evaluation_id=...`

- Load the evaluation via `EvaluationStore.get(sid, ...)` (unknown or foreign id is 404, same as doc 01); rebuild the bundle from the evaluation's stored pair + major key through the doc-01 bundle cache.
- Response `{"rows": [...], "omitted_no_rate": n, "cc_per_unit": 46.0, "target_per_unit": rate-or-null}`, rows as `ArbitrageRow.model_dump(mode="json")`.

## Tab UI

- Enable the ARBITRAGE tab from doc 03; fetch on first activation, cache in component state for the session.
- Prototype layout truth: headline "Take it at a community college instead", the explanatory line INCLUDING the "Savings are illustrative sample data." sentence (the cost table is curated, not billed truth; honesty rule), ranked cards with `#N`, course mapping line, units + `CitationTag`, and the teal "YOU SAVE" tile.
- `None`-dollar rows render the card without the teal tile, with the muted line "No per-unit rate published for this campus"; `omitted_no_rate` never applies client-side (the server already includes such rows; the count is displayed as a footnote only if non-zero).
- Types for the response join `lib/api.ts`; no new lib logic beyond a `formatRank` helper if needed; the ranking is server truth and is never re-sorted client-side.

## Tests

1. Contract tests: the standard valid/invalid fixture pair harness (`tests/contracts/test_arbitrage.py`).
2. `tests/transfer/test_arbitrage.py`: fixture-driven against the scenario bundles: untouched articulation ranks; partial series emits only the missing member; note-only and no-articulation cells are skipped; `None`-rate target yields `None` dollars and increments the omitted count; ordering pinned including the `None`-after-dollars rule; purity (same inputs, equal outputs).
3. `tests/app/test_routes.py` extension: the route round-trip on the fixture store; foreign-session 404.
4. Manual gate: for the verified demo evaluation, the top rows must be plausible against assist.org (spot-check the top three by hand) and the dollar math must equal `units * (291 - 46)` exactly.
