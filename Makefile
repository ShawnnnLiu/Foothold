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

# The pre-pivot `scripts/build_catalog.py` was retired with the Columbia
# bulletin pipeline on 2026-07-31. Its replacement, `scripts/build_articulation.py`,
# lands in increment 5 (implementation plan doc 02, split S9b), at which point
# this target invokes it. Failing loudly beats invoking a deleted script.
build-data:
	@echo "build-data is unavailable: the ASSIST build script lands in increment 5 (see docs/implementation-plans/articulation/02-assist-fetch-normalize-store.md)." >&2
	@exit 1
