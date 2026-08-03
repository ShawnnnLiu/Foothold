"""The curated cost table: shape validation, the loader, and the dollar
lookup seam the evaluator consumes."""

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from starmap.transfer.costs import CostTable, load_cost_table


def table_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "version": "costs-v1",
        "sources": [
            {
                "url": "https://example.edu/fees",
                "note": "example fee schedule",
                "retrieved": "2026-08-02",
            }
        ],
        "cc_per_unit_default": 46.0,
        "target_per_unit": {"7": 508.0},
    }
    payload.update(overrides)
    return payload


def test_valid_table_loads_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "costs.json"
    path.write_text(json.dumps(table_payload()), encoding="utf-8")
    table = load_cost_table(path)
    assert table.cc_per_unit_default == 46.0
    assert table.target_per_unit == {"7": 508.0}


def test_target_rate_hit_and_miss() -> None:
    table = CostTable.model_validate(table_payload())
    assert table.target_rate(7) == 508.0
    assert table.target_rate(39) is None


def test_unknown_version_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CostTable.model_validate(table_payload(version="costs-v2"))


def test_negative_default_rate_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CostTable.model_validate(table_payload(cc_per_unit_default=-1.0))


def test_negative_target_rate_is_rejected() -> None:
    with pytest.raises(ValidationError, match="negative"):
        CostTable.model_validate(table_payload(target_per_unit={"7": -508.0}))


def test_non_institution_id_key_is_rejected() -> None:
    with pytest.raises(ValidationError, match="not a positive institution id"):
        CostTable.model_validate(table_payload(target_per_unit={"UCSD": 508.0}))


def test_empty_sources_are_rejected() -> None:
    """Every figure must trace to a source URL (the user gate, doc 03)."""
    with pytest.raises(ValidationError):
        CostTable.model_validate(table_payload(sources=[]))


def test_undated_source_is_rejected() -> None:
    source = {"url": "https://example.edu/fees", "note": "n", "retrieved": "August 2026"}
    with pytest.raises(ValidationError):
        CostTable.model_validate(table_payload(sources=[source]))


def test_extra_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        CostTable.model_validate(table_payload(currency="USD"))
