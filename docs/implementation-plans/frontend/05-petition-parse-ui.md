# Increment F5: Petition Drawer + Transcript-Parse UI

Goal: the petition drawer and the LLM transcript-parse upgrade, executed ONLY after the two LLM nodes (`llm/petition_writer.py`, `llm/transcript_parser.py`) land from their own plan folder.
This doc locks the wire contracts NOW so the node increments and this UI increment build to the same seam without renegotiation.
Binding references: `docs/FOOTHOLD_PATHFINDERS_PLAN.md:145-162` (the two nodes, repair bounds, fallbacks), the HTTP policy in `CLAUDE.md` (LLM failure after repair exhaustion is 200 with `status: "failed"` and a typed `reason_code`), the prototype's `data-screen-label="Petition drawer"` section, and the vocabulary-gate axiom (the findings object given to the petition prompt IS the citation validator's vocabulary).

Execution precondition: both nodes merged with their FakeTransport suites green; live `ANTHROPIC_API_KEY` calls remain behind the user's go-ahead.
If the schedule forces cuts, this whole increment is cut-line 1 for the frontend: the drawer button stays disabled and the deterministic paste path from doc 03 remains.

## Locked wire contracts (implemented by the node increments, consumed here)

### `POST /api/evaluations/{evaluation_id}/petition`

- Body `{"finding_positions": [int]}`: indexes into the stored evaluation's `findings` array (the order is deterministic and stable, so positions are stable identifiers); min 1, each position must exist and reference an `at_risk` or `no_articulation` finding, else 422.
- Returns 202 `{"petition_id": "pet_..."}`; the job runs server-side against the stored findings only.
- 409 when the evaluation id is unknown to this session (uniform 404 semantics from doc 01 apply first).
  (Amended 2026-08-20: a POST for a selection whose petition is still pending no longer 409s; it returns 202 with the existing `petition_id`, per the decision 6 amendment in `../llm-nodes/00-overview.md`.)

### `GET /api/petitions/{petition_id}`

Poll shape, session-scoped like evaluations:

```json
{
  "status": "pending" | "succeeded" | "failed",
  "reason_code": null | "<LlmReasonCode>",
  "fallback": false,
  "letter_text": null | "full plain-text letter",
  "cited": [{"course_code": "...", "finding_position": 3}]
}
```

- `succeeded` with `fallback: true` is the deterministic template letter after repair exhaustion (still a 200/succeeded; the typed `reason_code` says why the LLM draft was discarded).
- `cited` lists every course code the citation validator confirmed in the letter, with its finding position; the UI underlines by exact string match of those codes only (the validator guarantees no other codes exist in the letter, so client-side matching cannot invent a citation).

### `POST /api/transcript/parse`

- Body `{"text": str, "sending_institution_id": int}` (text min 1, max 20000 chars; id > 0, the CC whose `cc_courses` vocabulary resolves the chips); 202 `{"parse_id": "parse_..."}`; poll `GET /api/transcript/{parse_id}`.
  (Amended 2026-08-03 by `docs/implementation-plans/llm-nodes/00-overview.md`: the original `{"text"}`-only body was unimplementable because resolution requires the institution; the UI already knows the CC from the landing screen.)
- Poll result: `status`/`reason_code` as above plus `chips: [{course_code, title, units_min, units_max, resolution: "exact" | "fuzzy_match"}]` and `unresolved: [{proposed_code, proposed_title}]`.
- Chips come pre-resolved through the same `cc_courses` vocabulary the autocomplete serves (the vocabulary gate); `unresolved` entries surface for manual fixing and never become chips automatically.

## Petition drawer UI

- Prototype layout truth: overlay + right drawer (600 px, amber offset shadow), title, "{n} of {m} items selected" line, checkbox list, letter card, copy button, counselor disclaimer.
- Checkbox list = the evaluation's at-risk and no-articulation findings (positions preserved); defaults: all `advisement_note`, `partial_series`, and `no_articulation` findings checked, others unchecked.
- Selection changes re-fire the POST (debounced 400 ms); while pending, the letter card shows a deterministic three-line skeleton, never spinner-only.
- Letter rendering: `letter_text` split on blank lines into paragraphs; within each paragraph, occurrences of `cited[].course_code` get the highlighter underline in their finding's hold color (amber for at-risk, red for no-articulation), mirroring the prototype's styling; the `fallback: true` state adds the line "Drafted from the template letter" above the card.
- Failure state (`status: "failed"`): the card shows the typed reason and a retry button; the drawer never fabricates a letter.
- Copy button copies `letter_text` verbatim with the prototype's "Copied" flip; the disclaimer line "This is a draft - verify with your counselor before submitting." is always visible.
- Enable the doc-03 sidebar button when this ships.

## Transcript-parse upgrade

- The doc-03 paste block gains a "Parse with AI" primary action beside the deterministic path; on 202 it polls at a fixed 1 s interval with a 30 s cap.
- Resolved chips merge through `lib/courses.ts` (dedupe applies); `fuzzy_match` chips render with an amber corner marker and their resolved title, and they carry `resolution: "fuzzy_match"` into the evaluation request so the evaluator's fuzzy-match at-risk classification fires.
  This requires doc 01's `POST /api/evaluations` request model to accept an optional `resolution` field per course, defaulting `"exact"`; add it in this increment with a test (the route still never trusts units or titles).
- Unresolved entries render as red-bordered non-chips with the proposed text and an edit affordance that drops the text into the autocomplete input.
- Repair exhaustion (`status: "failed"`) shows the typed reason and leaves the deterministic path untouched.

## Tests

- Backend: the wire contracts above get route tests with a FakeTransport-backed node (pending -> succeeded, repair-exhaustion fallback, failed, session isolation, position validation); no prompt-wording assertions (pinned-hash discipline lives in the node increments).
- Frontend vitest: selection-state transitions (default checks, toggle, positions payload); letter paragraph split + underline matching against a fixture poll response including the fallback and failed shapes; parse-poll reducer (pending/succeeded/failed/timeout) as a pure function.
- Manual gate: full demo flow ending in a letter whose every underlined code exists on the board, plus one forced-fallback run (FakeTransport or a scripted key failure) proving the template letter path renders honestly.
