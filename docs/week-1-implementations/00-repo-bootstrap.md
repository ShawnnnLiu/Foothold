# Increment 0: Repo Bootstrap

Goal: an empty-but-real backend package tree where `make check` is green, with CI parity from day one.
Roadmap source: `docs/IMPLEMENTATION_ROADMAP.md` increment 0.

## Permission gate

Before any `uv add`, ask the user once for the full Week 1 dependency surface: runtime `pydantic>=2`, `beautifulsoup4`, `anthropic`; dev `pytest`, `ruff`, `mypy`, `types-beautifulsoup4`.
If the user defers `anthropic`, proceed without it and record that increment 4 will re-ask.

## Directory tree to create

```
backend/
  .python-version                # exactly: 3.12
  pyproject.toml
  src/starmap/
    __init__.py                  # __version__ = "0.1.0"
    py.typed
    common/__init__.py
    contracts/__init__.py
    retrieval/__init__.py
    llm/__init__.py
    catalog/__init__.py
    prereqs/__init__.py
    pathways/__init__.py
    app/__init__.py
    app/web/__init__.py
  scripts/                       # empty until later increments
  tests/
    __init__.py
    test_package.py              # imports starmap and every region package
Makefile                         # repo root
.github/workflows/ci.yml
.gitignore
```

## pyproject.toml (locked content)

Historical locked content: the project was renamed to Foothold on 2026-08-01 and the live description differs.

```toml
[project]
name = "starmap"
version = "0.1.0"
description = "Astrolabe: Columbia course-selection helper (Stellic Pathfinders entry)"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.7",
    "beautifulsoup4>=4.12",
    "anthropic>=0.40",
]

[dependency-groups]
dev = [
    "pytest>=8",
    "ruff>=0.5",
    "mypy>=1.10",
    "types-beautifulsoup4",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/starmap"]

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]

[tool.mypy]
strict = true
mypy_path = "src"
packages = ["starmap"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Version floors are minimums for `uv add`; uv's lockfile (`uv.lock`, committed) is the actual pin.
Do not add config the tree does not need yet; extend these tables in later increments only when a tool demands it.

## Makefile (repo root, locked targets)

```make
.PHONY: test lint typecheck schema-check check build-data

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check src tests scripts && uv run ruff format --check src tests scripts

typecheck:
	cd backend && uv run mypy src tests scripts

schema-check:
	cd backend && uv run python scripts/generate_schemas.py --check

check: lint typecheck test schema-check

build-data:
	cd backend && uv run python scripts/build_catalog.py
```

Until increment 2 lands `generate_schemas.py`, `schema-check` must still succeed: create `backend/scripts/generate_schemas.py` now as a stub that accepts `--check` and exits 0 with the message `no contracts registered yet`.
Until increment 3 lands `build_catalog.py`, leave `build-data` out of `check` (it is never part of `check`) and let it fail with a clear file-not-found; do not stub it.
`mypy src tests scripts` requires `scripts/` to exist and typecheck; keep scripts strict-clean from the start.

## CI workflow (locked content)

`.github/workflows/ci.yml`:

```yaml
name: ci
on:
  push:
    branches: [main]
  pull_request:
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          python-version: "3.12"
      - run: cd backend && uv sync
      - run: make check
```

## .gitignore (repo root)

```
data/raw/
data/build/
backend/.venv/
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
```

`data/reports/`, `data/cache/`, `data/curated/`, and the two `.db` artifacts are committed and must NOT be ignored.

## First test

`backend/tests/test_package.py`: parametrize over the eight region module paths and `importlib.import_module` each; assert `starmap.__version__` is a non-empty string.
This exists so `make test` exercises a real collection pass, not an empty suite.

## Exit criteria

- `make check` green locally on the empty tree (lint, typecheck strict, pytest, schema-check stub).
- CI workflow file present; if the repo has no remote yet, note that CI proof lands on first push.
- `uv.lock` committed.
- One commit ending the increment (ask the user per the operating contract if standing autonomous-execution instructions are absent).
