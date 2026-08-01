# Week 1 Implementation Docs

PIVOT NOTICE (2026-07-31): the product pivoted to the Astrolabe transfer credit navigator (see `docs/STARMAP_PATHFINDERS_PLAN.md`); the roadmap was rewritten.
Per-doc status:

| Doc | Status after pivot |
|---|---|
| `00-repo-bootstrap.md` | Executed; unchanged. |
| `01-day1-risk-spikes.md` | Executed; historical record (the spike discipline is reused for the ASSIST spike). |
| `02-common-kernel-and-contracts.md` | Executed; kernel and machinery survive; the Columbia-shaped contracts (`course`, `offering`, `requirement_group`) are slated for retirement, and `prereq_expr` generalizes into `articulation_expr`. |
| `03-catalog-fetch-parse.md` | RETIRED and deleted 2026-07-31; recoverable in git history at commit 92998be. |
| `04-llm-backbone.md` | EXECUTED 2026-07-31, with one pivot correction: the closed node enum is `transcript_parser` / `petition_writer` (the doc's pre-pivot `prereq_extractor` / `pathway_proposer` name a retired node and a Mode C stretch node). `AGENTS.md` ("exactly two LLM nodes, both request-time") outranks the doc. The doc's locked prereq-extractor model config was dropped for the same reason; the `claude-sonnet-5` pricing it asked to record lives in `llm/transport_anthropic.py`, and the per-node `AdapterConfig` lands with its node in Week 2. |
| `05-prereq-extraction.md` | RETIRED and deleted 2026-07-31; recoverable in git history at commit 92998be. |
| `06-corpus-retrieval.md` | Applies at reduced scope (per-institution FTS5 over `cc_courses`; no interest queries, no eval set of interest-style queries). |
| `07-culpa-ingest.md` | RETIRED and deleted 2026-07-31; recoverable in git history at commit 92998be. |
| `SPLITS.md` | Superseded by the rewritten `docs/IMPLEMENTATION_ROADMAP.md`. |

The implementation docs for the ASSIST increments (4-7 in the rewritten roadmap) live in `docs/implementation-plans/articulation/`.
The "Globally locked decisions" below still bind except where they name retired Columbia-specific stages.

This folder turns the Week 1 increments of `docs/IMPLEMENTATION_ROADMAP.md` into executable implementation plans.
One doc per increment, written for a less-capable executor model per the conventions in `AGENTS.md` (section "Implementation Plan Conventions"): every design decision is locked here, the executor implements and does not design.

Authority order for an executing session: user chat instructions, `CLAUDE.md`, `AGENTS.md`, `docs/STARMAP_PATHFINDERS_PLAN.md` + `docs/STARMAP_TECH_REFERENCE.md`, these docs, `docs/specs/`, code.
These docs cite tech-reference sections instead of restating them; the tech reference is required reading for every session, so a citation like "TR 4.1" is a binding pointer, not optional background.

## Files

| Doc | Increment | Depends on |
|---|---|---|
| `00-repo-bootstrap.md` | Repo bootstrap: uv, package tree, Makefile, CI | nothing |
| `01-day1-risk-spikes.md` | CULPA spike + bulletin selector pinning (NETWORK) | 00 |
| `02-common-kernel-and-contracts.md` | `common/` kernel, contracts conventions, first six contracts | 00 |
| `03-catalog-fetch-parse.md` | RETIRED and deleted 2026-07-31; recoverable in git history at commit 92998be | - |
| `04-llm-backbone.md` | Generation engine, call log, transports, prompt pins | 02 |
| `05-prereq-extraction.md` | RETIRED and deleted 2026-07-31; recoverable in git history at commit 92998be | - |
| `06-corpus-retrieval.md` | Registry, snapshots, chunking, FTS5/BM25, eval, build stage 5 | 03 |
| `07-culpa-ingest.md` | RETIRED and deleted 2026-07-31; recoverable in git history at commit 92998be | - |
| `SPLITS.md` | Session splits with kickoff prompts and gates | all |

## Globally locked decisions

These apply to every increment and are not to be relitigated by executors.

### Toolchain and layout

- Python 3.12, pinned in `backend/.python-version`; uv-managed project rooted at `backend/` with package `backend/src/starmap/`.
- Region packages exactly as in the plan's repo layout: `common/`, `contracts/`, `retrieval/`, `llm/`, `catalog/`, `prereqs/`, `pathways/` (empty until Week 2), `app/web/` (empty until Week 2).
- Every package ships `py.typed`; mypy runs in strict mode; ruff is both linter and formatter.
- Scripts live in `backend/scripts/` (`build_catalog.py`, `generate_schemas.py`, `run_retrieval_eval.py`, `spike_fetch.py`) and are run via `uv run` from `backend/`.
- The Makefile lives at the repo root and delegates into `backend/`; targets: `test`, `lint`, `typecheck`, `schema-check`, `check` (all of the above), `build-data`.
- CI is GitHub Actions (`.github/workflows/ci.yml`) running `make check` on ubuntu-latest with `astral-sh/setup-uv`.
- Data lives at repo root: `data/raw/` (gitignored fetch cache), `data/build/` (gitignored scratch, including the build-time call log), `data/reports/` (committed, deterministic), `data/cache/` (committed LLM extraction cache), `data/curated/` (committed hand-written), `data/catalog.db`, `data/corpus.db` (committed artifacts).

### Dependency policy

Installing or changing any dependency requires user go-ahead (operating contract).
The full Week 1 dependency surface, requested once at increment 0: runtime `pydantic>=2`, `beautifulsoup4`, `anthropic` (imported only under `llm/`); dev `pytest`, `ruff`, `mypy`, `types-beautifulsoup4`.
HTTP fetching uses stdlib `urllib.request` (no requests/httpx dependency); FastAPI and frontend deps are Week 2.

### Committed-artifact identity (user-decided 2026-07-31)

`catalog.db` and `corpus.db` are committed as binary SQLite files.
The `--check` gate regenerates into a temp directory and compares canonical logical dumps, not raw bytes, because raw SQLite bytes vary across library versions.
`common/dbdump.py` owns the single canonical-dump definition (see doc 02); build discipline still enforces deterministic insert order, no timestamps in artifacts, and `VACUUM` before finalizing.

### The two LLM planes (user-decided 2026-07-31, recorded in AGENTS.md)

Claude Code and its subagents are the development plane only; they never perform extraction by hand.
The prereq extractor is an Anthropic API node run through `llm/engine.py` inside `make build-data`, pinned to model `claude-sonnet-5`.
Requires `ANTHROPIC_API_KEY`; the user registers at stellic.com/pathfinders for contest credits before increment 5.

### Extraction determinism and cost (locked here, detail in doc 05)

LLM output is nondeterministic, so byte-identical `catalog.db` regeneration is only possible through a committed extraction cache.
`data/cache/prereq_extractions.jsonl` stores every validated extraction keyed by `sha256(prompt_version, course_code, prereq_prose, sorted linked codes)`.
Stage 3 consults the cache first and only calls the API on misses or under `--refresh-prereqs`; `--check` therefore runs fully offline.
Extraction runs under a bounded worker pool of 8 threads (user-decided 2026-07-31); results are written in sorted course-code order so concurrency never affects artifacts.

### Conventions binding on all docs

- Contracts conventions per TR 4.5 wholesale: `extra="forbid"` + frozen, rebuild-through-validation, model-validator messages that name the field and quote offending values, one spec doc per contract in `docs/specs/`, generated JSON schemas with `--check`.
- The invalid-fixture pattern per TR 4.6: `backend/tests/fixtures/{valid,invalid}/<contract>/<name>.json` with `.expected.json` sidecars, one fixture per constraint.
- Typed errors only across region boundaries; every failure carries a `reason_code` from `contracts/reason_codes.py`.
- Markdown authored in this repo: one sentence per line, plain dash, never an em dash.

## Permission gates

| Gate | Increment | What to ask the user |
|---|---|---|
| Dependency install | 0 | The dependency list above, once |
| Live network: bulletin + CULPA probe | 1 | Go-ahead before the first request |
| Live network: full bulletin fetch (~80 pages) | 3 | Go-ahead (runs at 1 req/s on the cached-miss set) |
| Live Anthropic API | 5 | Go-ahead + confirm `ANTHROPIC_API_KEY` present and credits registered |
| Live network: CULPA ingest | 7 | Go-ahead, shaped by the spike decision |
| Commits | every increment | The user has standing instructions in SPLITS.md kickoffs; each split ends in exactly one commit |
