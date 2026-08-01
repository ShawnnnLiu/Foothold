"""Loader for the contract fixture harness.

Layout: `tests/fixtures/{valid,invalid}/<contract>/<name>.json`; every
invalid fixture has a `<name>.expected.json` sidecar containing
`{"error_substrings": [...]}`. A missing sidecar is a hard error, never a
silent skip.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Literal, NamedTuple

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures"


class FixtureCase(NamedTuple):
    contract_name: str
    path: Path
    payload: Any
    expected_substrings: list[str] | None


def iter_fixtures(
    kind: Literal["valid", "invalid"], contract: str | None = None
) -> Iterator[FixtureCase]:
    root = FIXTURES_ROOT / kind
    pattern = "*/*.json" if contract is None else f"{contract}/*.json"
    for path in sorted(root.glob(pattern)):
        if path.name.endswith(".expected.json"):
            continue
        payload = json.loads(path.read_text())
        expected: list[str] | None = None
        if kind == "invalid":
            sidecar = path.with_name(f"{path.stem}.expected.json")
            if not sidecar.exists():
                raise FileNotFoundError(f"missing expected sidecar {sidecar} for fixture {path}")
            expected = json.loads(sidecar.read_text())["error_substrings"]
        yield FixtureCase(path.parent.name, path, payload, expected)


def fixture_ids(case: FixtureCase) -> str:
    return f"{case.contract_name}/{case.path.stem}"
