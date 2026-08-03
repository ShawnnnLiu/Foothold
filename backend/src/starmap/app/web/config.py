"""App configuration (implementation plan frontend/01, "Files").

Paths default repo-relative so `make run` works from a fresh clone after
`make unpack-data`; every value can be overridden through its `FOOTHOLD_*`
environment variable, which is how tests and deploys point the app at other
databases without touching code.
"""

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[5]

_TRUTHY = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True, slots=True)
class AppConfig:
    articulation_db: Path
    corpus_db: Path
    sessions_db: Path
    costs_path: Path
    dist_dir: Path
    secure_cookies: bool


def _path(env: str, default: str) -> Path:
    raw = os.environ.get(env)
    return Path(raw) if raw else REPO_ROOT / default


def load_config() -> AppConfig:
    return AppConfig(
        articulation_db=_path("FOOTHOLD_ARTICULATION_DB", "data/articulation.db"),
        corpus_db=_path("FOOTHOLD_CORPUS_DB", "data/corpus.db"),
        sessions_db=_path("FOOTHOLD_SESSIONS_DB", "data/sessions.db"),
        costs_path=_path("FOOTHOLD_COSTS", "data/curated/costs.json"),
        dist_dir=_path("FOOTHOLD_DIST", "frontend/dist"),
        secure_cookies=os.environ.get("FOOTHOLD_SECURE_COOKIES", "").strip().lower() in _TRUTHY,
    )
