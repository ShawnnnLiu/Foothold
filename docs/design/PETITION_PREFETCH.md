# Petition Prefetch (Deferred Design, 2026-08-20)

Status: **not built**.
This records the considered-and-deferred "option B" for hiding the petition draft's ~10 s LLM latency, so the design is not re-derived later.
The shipped treatment is option A, the drafting-wait amendment in `ASCENT.md`: staged status line, wait hint, and pulsing skeleton inside the drawer.

## The idea

Fire the petition POST for the default selection as soon as the triage board mounts, cache the `petition_id` and its poll state, and when the user clicks "Draft petition letter" play the live-typing reveal immediately from the cached result.
The user's course state is frozen once an evaluation exists, so the default-selection letter is fully determined at board load.

## Why it was deferred

- **It only covers the first letter.**
  The drawer re-fires a fresh draft on every checkbox change ("the letter rebuilds as you check"), and "Edit courses" produces a new evaluation.
  Every interaction after the first click still waits the full draft time, so the option-A treatment is required regardless.
- **It spends LLM calls speculatively.**
  Every evaluation would trigger a petition draft even when the drawer is never opened.
  For a public prototype link (contest judges clicking through), that is real spend and call-log noise for letters nobody reads, against the project's cost-logging discipline.
- **The complexity is real.**
  The POST/poll lifecycle would have to lift out of `PetitionDrawer` into the triage screen or a shared cache module, keyed by `evaluation_id` plus the sorted selection key.

## Backend facts that shape the implementation

These are load-bearing; a naive frontend prefetch breaks on the first one.

- `POST /evaluations/{id}/petition` **attaches** whenever a petition for the same `(sid, evaluation_id, selection_key)` is reusable: it returns 202 with the existing `petition_id` instead of starting a duplicate job (amended 2026-08-20 and 2026-08-21; it originally returned 409 `petition_pending` while pending and spent a fresh LLM call once finished).
  Reusable means a live pending row (within the 120 s TTL) or any `succeeded` row with `fallback: false` (no TTL); failed rows and fallback letters always start fresh so Retry works.
  A prefetch could therefore just re-POST: the server dedupes both the in-flight and the completed case, so a frontend cache module is no longer required for spend safety (the speculative-spend objection above, drafts for drawers never opened, still stands).
- The selection key is the ascending-sorted positions list (`toggleSelection` keeps payloads sorted for exactly this reason), so the cache key is stable across UI event ordering.

## Sketch, if it is ever built

1. A small React-free cache module in `frontend/src/lib/` holding `{evaluationId, selectionKey} -> {petitionId, result | pending}`.
2. Triage mounts, computes `defaultSelection(petitionItems(evaluation))`, and if non-empty starts the POST + poll loop into the cache.
3. `PetitionDrawer` consults the cache before POSTing: a cached success plays the typing reveal immediately; a cached pending entry shows the option-A drafting state and joins the existing poll loop; a miss (any non-default selection) follows today's live path.
4. Cache entries are keyed by evaluation, so "Edit courses" invalidates naturally; drawer close must not abandon the shared loop while the cache owns it.
5. Scope stays default-selection-only; prefetching per checkbox combination is combinatorial spend for no realistic win.

## Decision

Deferred on 2026-08-20 in favor of option A.
Revisit only if the click-to-letter moment must be instant (e.g. a live on-stage demo), and then implement exactly the attach-don't-repost shape above.
