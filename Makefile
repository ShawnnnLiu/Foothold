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
