# Foothold

**Foothold reads the transfer rules so students don't lose the credits they already paid for.**

Live app: **[foothold-transfer.com](https://foothold-transfer.com)** · Demo video: **[watch on YouTube](https://www.youtube.com/watch?v=Jop91D81H2c)**

Built solo by [Xiangjian (Shawn) Liu](https://shawnnnliu.github.io/) for the [Stellic Pathfinders challenge](https://www.stellic.com/pathfinders), category **Overcoming Obstacles**.
Every line in this repository was written inside the submission window (Jul 20 - Aug 21, 2026).

## The problem

Every year about 80,000 Californians transfer from a community college to a UC or CSU.
The GAO found that transfer students lose, on average, 43 percent of their credits (GAO-17-574), and half of them are on Pell grants, so lost credits are lost aid money on top of lost time.
The rules that decide what transfers are public.
They sit in articulation agreements on ASSIST.org, thousands of them, and almost nobody reads them before applying.

## What Foothold does

A student picks her community college, target university, and major, then adds her courses as chips or pastes her transcript straight from the portal.
Foothold checks every course against the official articulation agreement, line by line, and lays the verdicts out on a climbing wall: **transfers cleanly**, **at risk**, **no articulation**, plus what she still owes for the major, in units and dollars.
Every verdict is clickable and shows its citation into the agreement (agreement key, articulation position, academic year).

From the at-risk findings, Foothold drafts a credit appeal letter she can hand to a counselor.
A citation validator rejects any draft that cites a course or agreement fact not in the deterministic findings; if drafting fails validation twice, a plain deterministic template is used instead.
A wrong citation makes an appeal worse than no letter at all, so no unvalidated sentence ever reaches the student.

A second mode inverts the same index for students already enrolled at a university: which community college courses articulate back into your degree, ranked by dollars saved.

**Try it:** open [foothold-transfer.com](https://foothold-transfer.com) and press the demo button on the landing page to load a real route, or build your own from any covered college.
In the canonical demo, a De Anza student headed to UCSD computer science finds nine units of C++ that articulate to nothing (the agreement wants the Java path) and an assembly-language series she is two-thirds through, which counts as zero until the last course is done.
Caught now, that is about a $340 fix at De Anza.
Caught after transfer, it is a $15,686 extra quarter at UCSD.

## The rule that shaped the build

> LLMs propose. Deterministic infrastructure disposes.
> The AI never decides what transfers; the articulation agreement does.

- Transfer verdicts come from a deterministic evaluator over validated articulation expression trees.
  There is no LLM anywhere in the verdict path, the retrieval path, or the data build pipeline.
- The corpus is **31,236 agreements** and **352,024 articulation rows**, covering **115 California community colleges** into **all nine UC campuses and the six largest CSUs**, fetched politely from ASSIST's public API and committed as read-only SQLite artifacts.
- Claude appears at exactly two request-time edges: transcript text in, petition letter out.
  The shipped UI resolves pasted course codes deterministically; Claude drafts only the letter's prose, and even that passes the citation validator before anyone sees it.
- Every LLM call is bounded (at most 2 repair attempts, then a typed fallback), logged with tokens and cost, and every failure carries a typed `reason_code`.
- Advisement notes in an agreement are never silently satisfied: they downgrade a match to at-risk and are always surfaced.

## Run it locally

Requirements: Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 20+.

```bash
make unpack-data                          # restore data/articulation.db from the committed gzip (first thing on a fresh clone)
cd frontend && npm ci && npm run build && cd ..
make run                                  # serves app + API at http://localhost:8000
```

Everything except letter drafting runs fully offline over the committed databases.
Drafting calls the Claude API and needs `ANTHROPIC_API_KEY` exported; without it the app still runs, and petition requests return a typed "LLM features are disabled" failure.

For frontend development with hot reload, run `make run` in one terminal and `cd frontend && npm run dev` in another (Vite proxies `/api` to port 8000).

## Repository tour

| Path | What it is |
|---|---|
| `backend/src/starmap/` | FastAPI backend (the package keeps the pre-pivot codename `starmap`) |
| &nbsp;&nbsp;`contracts/` | Frozen Pydantic models, one module per spec, `extra="forbid"` |
| &nbsp;&nbsp;`assist/` | ASSIST fetch (1 req/s, on-disk cache), normalization, and the deterministic data build |
| &nbsp;&nbsp;`transfer/` | The evaluator, triage view-model, cost table, and arbitrage |
| &nbsp;&nbsp;`retrieval/` | FTS5/BM25 index for fuzzy course resolution |
| &nbsp;&nbsp;`llm/` | The only package allowed to import the LLM SDK: engine, call log, transcript parser, petition writer |
| &nbsp;&nbsp;`app/web/` | Routes, session middleware (server-minted HttpOnly cookie, no sign-in), SPA serving |
| `frontend/` | React + Vite; all logic lives in unit-tested React-free `lib/` modules, screens are thin renderers |
| `data/` | Committed build artifacts: `articulation.db.gz` (~319 MB unpacked), `corpus.db`, curated `costs.json`; `sessions.db` is the only mutable database |
| `docs/` | Product plan, mechanism-level tech reference, schema specs, testing strategy |
| `Makefile`, `Dockerfile`, `fly.toml` | Checks, container build, and the Fly.io deployment (single always-on machine) |

## Trust and testing

**953 automated tests** (865 backend, 88 frontend) sit behind the verdicts, including one named fixture per evaluation reason code, partial-series and advisement semantics, the repair loop against a fake transport, and the session trust boundary.

```bash
make check        # lint + typecheck + pytest + schema parity + fixture parity
cd frontend && npm test
```

Committed artifacts regenerate byte-identically from the cached ASSIST data; every generator has a `--check` mode.
The demo evaluation is pinned cross-language: the backend recomputes it and compares against the committed frontend fixtures on every `make check`.

## AI tools used (full disclosure)

- **Claude Code (Fable 5)** for development.
- **Claude Design** for UI design.
- **Claude in Chrome** for browser testing.
- **Claude API (claude-sonnet-5)** in-product, for the two LLM edges described above.
- **ElevenLabs** for the demo video voiceover.
- **Adobe Podcast Enhance** for voiceover audio cleanup.
- **CapCut auto-captions** for the demo video captions.
