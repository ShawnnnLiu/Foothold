"""Static gate: the LLM SDK import stays confined to one module.

`CLAUDE.md` states "only `llm/` may import the LLM SDK" in prose. This walks the
real source tree so the rule is enforced rather than asserted.
"""

import ast
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src" / "starmap"
SDK_ROOT_MODULE = "anthropic"
# The single sanctioned SDK import site, relative to `src/starmap`.
SDK_IMPORT_SITE = "llm/transport_anthropic.py"


def imported_root_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def modules_importing(root_module: str) -> set[str]:
    return {
        path.relative_to(SRC_ROOT).as_posix()
        for path in sorted(SRC_ROOT.rglob("*.py"))
        if root_module in imported_root_modules(path)
    }


def test_sdk_is_imported_only_at_the_sanctioned_site() -> None:
    assert modules_importing(SDK_ROOT_MODULE) == {SDK_IMPORT_SITE}


def test_the_walk_actually_sees_source_files() -> None:
    """Guard against a vacuous pass if the tree layout ever moves."""
    assert len(list(SRC_ROOT.rglob("*.py"))) > 10
    assert (SRC_ROOT / SDK_IMPORT_SITE).exists()
