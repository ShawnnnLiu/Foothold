"""Static gates: the region boundaries `CLAUDE.md` states in prose, enforced.

Three rules, all walked over the real source tree rather than asserted:

1. The LLM SDK import is confined to one module.
2. `urllib` is confined to the ASSIST network boundary, which is what keeps the
   "fakes are allowed at external boundaries only" testing rule meaningful: a
   second module reaching the network would be a seam nothing fakes.
3. Region packages do not import sibling regions; cross-region communication
   goes through `contracts/` and `common/`.
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "starmap"
SDK_ROOT_MODULE = "anthropic"
# The single sanctioned SDK import site, relative to `src/starmap`.
SDK_IMPORT_SITE = "llm/transport_anthropic.py"
# `http.py` is the network boundary; `corridor.py` percent-encodes agreement
# keys, which is url building rather than url opening.
URLLIB_IMPORT_SITES = {"assist/http.py", "assist/corridor.py"}
# The two regions every other region is allowed to depend on.
SHARED_REGIONS = frozenset({"common", "contracts"})


def imported_root_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def imported_regions(path: Path) -> set[str]:
    """The `starmap.<region>` packages this file imports.

    Relative imports are intra-package by construction and so are never a
    sibling-region crossing; the tree uses absolute imports throughout anyway.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    parts = (name.split(".") for name in names)
    return {part[1] for part in parts if part[0] == "starmap" and len(part) > 1}


def region_of(path: Path) -> str:
    """The region a source file belongs to; `""` for top-level modules."""
    relative = path.relative_to(SRC_ROOT).parts
    return relative[0] if len(relative) > 1 else ""


def modules_importing(root_module: str) -> set[str]:
    return {
        path.relative_to(SRC_ROOT).as_posix()
        for path in sorted(SRC_ROOT.rglob("*.py"))
        if root_module in imported_root_modules(path)
    }


def test_sdk_is_imported_only_at_the_sanctioned_site() -> None:
    assert modules_importing(SDK_ROOT_MODULE) == {SDK_IMPORT_SITE}


def test_urllib_is_confined_to_the_assist_network_boundary() -> None:
    assert modules_importing("urllib") == URLLIB_IMPORT_SITES


def test_regions_do_not_import_sibling_regions() -> None:
    violations = {
        path.relative_to(SRC_ROOT).as_posix(): sorted(
            imported_regions(path) - SHARED_REGIONS - {region_of(path)}
        )
        for path in sorted(SRC_ROOT.rglob("*.py"))
        if imported_regions(path) - SHARED_REGIONS - {region_of(path)}
    }
    assert violations == {}


def test_the_walk_actually_sees_source_files() -> None:
    """Guard against a vacuous pass if the tree layout ever moves."""
    assert len(list(SRC_ROOT.rglob("*.py"))) > 10
    assert (SRC_ROOT / SDK_IMPORT_SITE).exists()
    assert all((SRC_ROOT / site).exists() for site in URLLIB_IMPORT_SITES)
    assert imported_regions(SRC_ROOT / "assist" / "fetch.py") == {"assist", "common", "contracts"}
