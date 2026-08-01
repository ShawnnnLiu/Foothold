# Week 1 Session Splits

Per `AGENTS.md` "Implementation Plan Conventions": each split is one fresh Claude Code session ending in exactly one commit, sized at planning time to roughly 300k total session tokens or less including reads, edits, test iteration, and gates.
Fixed per-session overhead assumed for every budget below: `CLAUDE.md` + `AGENTS.md` + this plan folder's relevant doc + tech-reference sections + named source files, roughly 60-80k tokens before the first edit.
Sizing verified against the docs as written 2026-07-31; executors trust named symbols over line numbers if drift appears.

Standing execution rules for every kickoff: read the named docs before editing; respect the permission gates (dependencies, network, API); end with `make check` green and one commit; if a split is dying mid-work, land the named fallback boundary instead of pushing on.

## S0: bootstrap (doc 00) - small, ~120k

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/week-1-implementations/README.md`, and `docs/week-1-implementations/00-repo-bootstrap.md`.
> Execute increment 0 exactly as specified: ask me once for the dependency install, then build the tree, Makefile, CI workflow, and the schema-check stub.
> Gate: `make check` green.
> End with one commit: `Bootstrap backend package, toolchain, and CI`.

## S1: risk spikes (doc 01) - small, ~100k, NETWORK

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/week-1-implementations/01-day1-risk-spikes.md`.
> Ask me for network go-ahead, then run both spikes at 1 req/s and write `docs/notes/day1_spikes.md` per the template, including the CULPA decision matrix row and the final course-code regex.
> End with one commit: `Record day-1 spike findings: CULPA decision, bulletin selectors`.

## S2a: common kernel + machinery (doc 02 parts 1-2) - medium, ~200k

Scope: `common/` (errors, sqlite, clock, ids, dbdump), `contracts/base.py`, `contracts/dedup.py`, `contracts/codes.py`, test support twins, kernel tests.
Fallback boundary: kernel green without `dbdump.py` (land it in S2b if squeezed).

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/STARMAP_TECH_REFERENCE.md` section 4.3 and 4.5, and `docs/week-1-implementations/02-common-kernel-and-contracts.md` parts 1-2.
> Implement the kernel and contracts machinery exactly as locked; do not add generality the doc does not name.
> Gate: `make check` green including the kernel test list.
> End with one commit: `Add common kernel and contracts machinery`.

## S2b: six contracts + fixtures + schemas (doc 02 parts 3-5) - large, ~280k

Scope: six contracts, six spec docs, full fixture inventory, real `generate_schemas.py`.
Fallback boundary: land `reason_codes` + `prereq_expr` + `course` with specs, fixtures, and schema generation wired; remaining three contracts become a follow-up commit in the same pattern.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, tech reference 4.5-4.6 and 1.1, `docs/notes/day1_spikes.md` (final course-code regex), and `docs/week-1-implementations/02-common-kernel-and-contracts.md` parts 3-5.
> Spec first, then model, then fixtures, then schemas, then tests, per contract.
> Gate: `make check` green; one invalid fixture per constraint proven.
> End with one commit: `Add first six contracts with specs, fixtures, and generated schemas`.

## S3: catalog fetch + parse (doc 03) - large, ~280k, NETWORK for the full fetch

Fallback boundary: fetcher + parser + store green on the 5 spike departments before scaling to all; the all-departments fetch and the spot-check note can be the last steps.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/notes/day1_spikes.md`, and `docs/week-1-implementations/03-catalog-fetch-parse.md`.
> Build fetch, parse, store, and build stages 1-2 exactly as locked; ask me before the full ~80-page fetch.
> Gates: `make check` green; parse report reviewed; spot-check note written.
> End with one commit: `Add catalog fetch, parse, and store; build stages 1-2`.

## S4: LLM backbone (doc 04) - large, ~280k

Fallback boundary: engine + call log + FakeTransport tests green before the Anthropic transport and prompt-pin scaffold.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, tech reference 4.1, 4.2, 4.6, and `docs/week-1-implementations/04-llm-backbone.md`.
> Implement the engine outcome table exactly; no live API calls; the SDK import stays confined to `llm/transport_anthropic.py`.
> Gate: the full engine test list green under `make check`.
> End with one commit: `Add LLM generation engine, call log, and transports`.

## S5: prereq extraction (doc 05) - large, ~280k, NETWORK (Anthropic API)

Fallback boundary: expr eval + validator + node + cache green offline against FakeTransport; the live full-catalog run and verification note are the final steps and need my go-ahead plus `ANTHROPIC_API_KEY`.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, tech reference 4.1 and the plan's prereq pipeline section, plus `docs/week-1-implementations/05-prereq-extraction.md`.
> Build expr evaluation, the extraction validator, the extractor node with pinned prompts, the committed extraction cache, and stage 3 with the 8-worker pool.
> Ask me before any live API call; run the full extraction once approved; then hand-verify the demo majors and write the verification note.
> Gates: `make check` green; `--check` byte-identical offline; fallback rate reviewed.
> End with one commit: `Add prereq extraction propose/dispose pipeline`.

## S6: corpus + retrieval (doc 06) - large, ~290k

Fallback boundary: registry + chunking + index green with their full TR test lists before the corpus build stage and eval floors.

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, tech reference section 1 including the Starmap deltas, and `docs/week-1-implementations/06-corpus-retrieval.md`.
> Implement the retrieval stack and build stage 5 exactly as locked; author the evalset against the real corpus; measure and pin floors.
> Gates: `make check` green including `retrieval-eval --strict`; `corpus.db` `--check` proven.
> End with one commit: `Add corpus store, FTS5 retrieval, and eval harness`.

## S7: CULPA + milestone close (doc 07) - medium, ~200k, NETWORK

Kickoff:

> Read `CLAUDE.md`, `AGENTS.md`, `docs/notes/day1_spikes.md` (the CULPA decision), and `docs/week-1-implementations/07-culpa-ingest.md`.
> Implement only the branch the spike decision selected; ask me before any CULPA network traffic.
> Gates: `make build-data` green end-to-end; both artifacts committed with `--check` green; all reports reviewed.
> End with one commit: `Add CULPA ingest; complete Week 1 data build`.
