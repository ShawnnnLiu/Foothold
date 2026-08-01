# Articulation Session Splits

Per `AGENTS.md` "Implementation Plan Conventions": each split is one fresh Claude Code session ending in exactly one commit, sized at planning time to roughly 300k total session tokens or less including reads, edits, test iteration, and gate runs.
Fixed per-session overhead assumed in every budget: `CLAUDE.md` + `AGENTS.md` (~12k) + this folder's overview and relevant doc (~20-30k) + the named source, spec, and test files read before the first edit (~30-50k), so roughly 60-90k before any edit.
Sizing performed 2026-07-31 against `main` at commit `4762feb`; executors trust named symbols over line numbers if drift appears.

Standing execution rules for every kickoff: read the named docs before editing; respect the permission gates in `00-overview.md`; markdown one sentence per line, plain dash, never an em dash; end with `make check` green and exactly one commit; never add a co-author line; if a split is dying mid-work, land the named fallback boundary instead of pushing on.

## S8a: expression generalization + Columbia retirement (doc 01 parts 1-4) - medium, ~230k

Scope: the doc 01 deletion list, `codes.py` rewrite, `articulation_expr.py` with spec/fixtures/tests, the reason-code rework with spec update, schema regeneration for the shrunken registry, `test_generate_schemas.py` and `test_codes.py` and `test_reason_codes.py` updates.
Fallback boundary: none; this split is atomic (deletions and the expression rename must land together or `make check` breaks).

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/implementation-plans/articulation/00-overview.md`, and `docs/implementation-plans/articulation/01-articulation-contracts.md` parts 1-4, plus `backend/src/starmap/contracts/prereq_expr.py`, `codes.py`, `reason_codes.py`, their specs in `docs/specs/`, and `backend/tests/contracts/test_prereq_expr.py`.
> Execute exactly: delete the locked file list, rewrite `codes.py`, create `articulation_expr` (spec, model, fixtures, tests), rework `reason_codes.py` with its spec, and regenerate `backend/schemas/`.
> Gate: `make check` green; no `prereq_expr`/`course`/`offering`/`requirement_group` references remain under `backend/`.
> End with one commit: `Generalize prereq_expr into articulation_expr; retire Columbia contracts`.

## S8b: institution, agreement, articulation contracts (doc 01 part 5, first three) - large, ~270k

Scope: `institution.py`, `agreement.py` (including the template-asset models), `articulation.py`, their three specs, valid fixtures transcribed from the ASSIST captures, the full invalid-fixture inventories, schema registry additions, and `test_assist_fixture_alignment.py`.
Fallback boundary: land `institution` + `agreement` complete (spec, fixtures, schemas, tests, registry) and leave `articulation` plus the alignment test to S8c; state the carry-over in the commit body.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/implementation-plans/articulation/00-overview.md` (the fixture table and payload facts), `docs/implementation-plans/articulation/01-articulation-contracts.md` part 5, TR 4.5-4.6, the ASSIST fixtures `institutions.json`, `agreement_major_cse_cs_113_to_7_y76.json`, `agreement_dept_math_113_to_7_y76.json`, and `backend/tests/support/fixtures.py`.
> Implement `institution`, `agreement` (with template-asset models), and `articulation` exactly as locked: spec first, then model, fixtures, schemas, tests.
> Gate: `make check` green; every locked validator has a firing invalid fixture; `test_assist_fixture_alignment.py` green.
> End with one commit: `Add institution, agreement, and articulation contracts from ASSIST fixtures`.

## S8c: course projections + evaluation contract (doc 01 parts 5-6, remainder) - large, ~260k

Scope: `cc_course.py`, `target_course.py`, `evaluation.py`, their specs, fixtures, schema registry finalization to the locked eight-name set, and the `test_generate_schemas.py` final state.
Fallback boundary: land `cc_course` + `target_course` complete; `evaluation` becomes the follow-up commit in the same pattern.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/implementation-plans/articulation/00-overview.md`, `docs/implementation-plans/articulation/01-articulation-contracts.md` part 5 (`cc_course`, `target_course`, `evaluation`) and part 6, plus the merged `contracts/reason_codes.py`, `contracts/articulation.py`, and `backend/scripts/generate_schemas.py`.
> Implement the three contracts exactly as locked, including the `BUCKET_FOR_CODE` validator and the citation-requirement validator on `Finding`.
> Gate: `make check` green; the committed schema set is exactly the locked eight files.
> End with one commit: `Add cc_course, target_course, and evaluation contracts`.

## S9a: ASSIST fetcher (doc 02 through "corridor.py") - medium, ~240k

Scope: `assist/` package skeleton, `errors.py`, `http.py` with `FakeHttpTransport`, `fetch.py` (session bootstrap, cache, manifest, pacing, offline mode, endpoint builders), `corridor.py`, and the full fetcher test list.
No network anywhere in this split.
Fallback boundary: land `http.py` + `fetch.py` without the corridor walk; the walk moves to S9b.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/implementation-plans/articulation/00-overview.md`, `docs/implementation-plans/articulation/02-assist-fetch-normalize-store.md` through the corridor section, `docs/notes/assist_spike.md` (access mechanics and endpoints), and `backend/src/starmap/common/sqlite.py` and `clock.py`.
> Implement the transport seam, session bootstrap with the XSRF echo and 400-refresh rule, the URL-hash cache with manifest, 1 req/s pacing, offline mode, and the corridor constants, exactly as locked; zero live requests.
> Gate: `make check` green including the fetcher test list.
> End with one commit: `Add ASSIST fetcher: session bootstrap, cache, corridor scope`.

## S9b: normalize + store + build script (doc 02 remainder, offline) - large, ~290k

Scope: `normalize.py` (envelope, double-decode, expression mapping, fixture-pending `advisement_texts`, template assets, projections), `store.py`, `report.py`, `scripts/build_articulation.py` with `--check`, Makefile updates, deletion of the empty `catalog/` package, and the full offline test list against the captured fixtures.
Fallback boundary: normalize green on both captured agreement fixtures (tests passing) before store and the build script; if squeezed, commit normalize alone with the store carried to a follow-up commit.
End-of-split action: propose (do not execute) the `beautifulsoup4` removal to the user.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/implementation-plans/articulation/00-overview.md`, all of `docs/implementation-plans/articulation/02-assist-fetch-normalize-store.md`, `docs/notes/assist_spike.md` (payload model and implications), the two agreement fixtures in `backend/tests/fixtures/assist/`, and `backend/src/starmap/assist/` as landed by S9a plus `common/dbdump.py`.
> Implement normalize, store, report, and the build script exactly as locked, offline only; the advisement mapping must raise `advisement_shape_unknown` on any non-empty attributes list.
> Gate: `make check` green; the store-determinism and fault-isolation tests green; `--check` proves itself on a fixture-built db.
> End with one commit: `Add ASSIST normalize, articulation store, and build pipeline`.

## S9c: live corridor fetch + advisement pinning - medium, ~200k, NETWORK

Scope: the doc 02 "Split S9c" workflow: gated full fetch, build, advisement fixture capture and pinning, spot checks, artifact commit.
This split commits `data/articulation.db`, the build report, the new advisement fixture, and `docs/notes/articulation_spotchecks.md`.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/implementation-plans/articulation/00-overview.md` (permission gates), and the "Split S9c" section of `docs/implementation-plans/articulation/02-assist-fetch-normalize-store.md`.
> Ask me for the network go-ahead, then run the corridor fetch at 1 req/s, build, review the report with me, capture and pin the advisement fixture, rebuild, spot-check the demo pair against assist.org, and run `make build-check`.
> Confirm the artifact size with me before committing.
> End with one commit: `Fetch ASSIST corridor; build and commit articulation.db`.

## S10a: evaluator core (doc 03 through units accounting) - large, ~280k

Scope: `transfer/` package, `evaluate.py` (expression evaluation, classification, units), deletion of the empty `prereqs/` package, the per-reason-code fixture scenarios, and the direct `evaluate_expr` unit tests.
Fallback boundary: `evaluate_expr` plus the fixture harness green before the classification algorithm; if squeezed, commit expression evaluation alone.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/implementation-plans/articulation/00-overview.md`, `docs/implementation-plans/articulation/03-transfer-evaluator.md` through the units section, `docs/specs/evaluation.schema.md`, `backend/src/starmap/contracts/articulation_expr.py` and `evaluation.py`, and `docs/TESTING_STRATEGY.md`.
> Implement the locked expression semantics, classification order, and units accounting exactly; one fixture scenario per `EvaluationFindingCode` plus the named edge scenarios.
> Gate: `make check` green; every finding code proven by its named fixture.
> End with one commit: `Add deterministic transfer evaluator with per-code fixtures`.

## S10b: triage, costs, demo verification (doc 03 remainder) - medium, ~210k

Scope: `costs.py` + `data/curated/costs.json` (numbers are a user gate), `triage.py`, `scripts/evaluate_student.py`, the demo student file, and the hand-verification note.
This split needs the S9c artifact; run it after S9c.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/implementation-plans/articulation/00-overview.md` (permission gates), and the costs, triage, CLI, and exit-criteria sections of `docs/implementation-plans/articulation/03-transfer-evaluator.md`.
> Build the cost table with figures and source URLs I confirm in-session, the triage view-model, and the CLI; finalize the demo student per the locked composition criteria; evaluate it and hand-verify every finding against assist.org, recording the checks in `docs/notes/evaluator_verification.md`.
> Gate: `make check` green; the CLI milestone run verified.
> End with one commit: `Add triage board, cost table, and verified demo evaluation`.

## S11: fuzzy matcher + corpus artifact (doc 04) - large, ~260k

Scope: `retrieval/` (errors, index, resolve), the corpus build stage in `build_articulation.py`, the resolver case fixtures, the full retrieval test list, and the committed `data/corpus.db`.
Fallback boundary: index + resolver green on temp dbs before the corpus stage and artifact commit.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/implementation-plans/articulation/00-overview.md`, all of `docs/implementation-plans/articulation/04-fuzzy-course-matcher.md`, TR 1.4 and 1.6, and `backend/src/starmap/assist/store.py`.
> Implement the per-institution index and the fixed-threshold resolver exactly as locked (`FUZZY_ACCEPT_RATIO = 0.6` is not tunable); wire `--stage corpus`; run `make build-check` over both artifacts.
> Confirm the `corpus.db` size with me before committing, then remind me about the dormant `corpus_document` contract (standing decision point).
> End with one commit: `Add per-institution FTS5 course matcher; build and commit corpus.db`.
