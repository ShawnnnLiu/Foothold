import importlib

import pytest

import starmap

REGION_MODULES = [
    "starmap.common",
    "starmap.contracts",
    "starmap.retrieval",
    "starmap.llm",
    "starmap.assist",
    "starmap.transfer",
    "starmap.pathways",
    "starmap.app.web",
]


@pytest.mark.parametrize("module_path", REGION_MODULES)
def test_region_package_imports(module_path: str) -> None:
    assert importlib.import_module(module_path) is not None


def test_version_is_nonempty_string() -> None:
    assert isinstance(starmap.__version__, str)
    assert starmap.__version__
