.PHONY: test lint typecheck schema-check check build-data build-check

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check src tests scripts && uv run ruff format --check src tests scripts

typecheck:
	cd backend && uv run mypy src tests scripts

schema-check:
	cd backend && uv run python scripts/generate_schemas.py --check

check: lint typecheck test schema-check

# Offline and cache-driven: every stage reads `data/raw/assist/`, and live
# ASSIST requests need `--allow-network`, which is a user permission gate.
build-data:
	cd backend && uv run python scripts/build_articulation.py --stage all

# The LOCAL committed-artifact gate: rebuild from the same cache and compare
# canonical dumps. It needs the raw cache, which is gitignored and far too
# large to commit, so this is deliberately NOT wired into CI; run it before
# any commit that touches `data/articulation.db` or the build report.
build-check:
	cd backend && uv run python scripts/build_articulation.py --check
