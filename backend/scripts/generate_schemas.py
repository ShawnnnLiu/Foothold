"""Generate JSON schemas for contract models.

Output bytes per contract are exactly
`json.dumps(model.model_json_schema(mode="serialization"), indent=2, sort_keys=True) + "\n"`;
that exact recipe IS the byte-determinism mechanism. `--check` recomputes
and exits non-zero listing `missing:` / `out of date:` files.
"""

import argparse
import json
from pathlib import Path

from pydantic import BaseModel

from starmap.contracts.agreement import Agreement
from starmap.contracts.articulation import Articulation
from starmap.contracts.articulation_expr import ArticulationExprRoot
from starmap.contracts.corpus_document import CorpusDocument
from starmap.contracts.institution import Institution
from starmap.contracts.llm_call_log import LlmCallLogRecord

# Nested models are not registered separately: `ReceivingCourse` is reachable
# through `articulation`. The template-asset models are the exception - the
# `Agreement` envelope holds no template field, so `RequirementGroupAsset` is
# reachable from nothing registered and ships no generated schema. Doc 01 part
# 6 locks the registry to exactly this name set, and its parenthetical
# rationale ("reachable through their parents' schemas") does not hold for the
# template models; the name set is the decision, so it stands.
CONTRACTS: dict[str, type[BaseModel]] = {
    "agreement": Agreement,
    "articulation": Articulation,
    "articulation_expr": ArticulationExprRoot,
    "corpus_document": CorpusDocument,
    "institution": Institution,
    "llm_call_log": LlmCallLogRecord,
}

DEFAULT_SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"


def render_schema(model: type[BaseModel]) -> str:
    schema = model.model_json_schema(mode="serialization")
    return json.dumps(schema, indent=2, sort_keys=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate JSON schemas for contract models.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify committed schemas match regenerated output",
    )
    parser.add_argument(
        "--schemas-dir",
        type=Path,
        default=DEFAULT_SCHEMAS_DIR,
        help="directory holding <name>.schema.json files",
    )
    args = parser.parse_args(argv)

    if args.check:
        missing: list[Path] = []
        out_of_date: list[Path] = []
        for name, model in sorted(CONTRACTS.items()):
            path = args.schemas_dir / f"{name}.schema.json"
            if not path.exists():
                missing.append(path)
            elif path.read_text() != render_schema(model):
                out_of_date.append(path)
        for path in missing:
            print(f"missing: {path}")
        for path in out_of_date:
            print(f"out of date: {path}")
        if missing or out_of_date:
            return 1
        print(f"{len(CONTRACTS)} schemas up to date")
        return 0

    args.schemas_dir.mkdir(parents=True, exist_ok=True)
    for name, model in sorted(CONTRACTS.items()):
        path = args.schemas_dir / f"{name}.schema.json"
        path.write_text(render_schema(model))
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
