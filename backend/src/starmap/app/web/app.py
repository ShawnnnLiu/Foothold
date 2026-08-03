"""FastAPI app assembly in the pinned order (TR 4.4, adapted by doc 01).

The order is load-bearing: the SPA catch-all matches everything and routes
resolve in registration order, so it mounts LAST, and only when a built
`index.html` exists (API-only test builds keep clean 404s on non-API paths).

`create_app` opens its databases eagerly: lazy opening would hide
misconfiguration until the first request. `dev_app` is exposed through module
`__getattr__` so `uvicorn starmap.app.web.app:dev_app` builds the real app on
attribute access while importing `create_app` (as every test does) opens no
database.
"""

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from starmap.app.web.config import AppConfig, load_config
from starmap.app.web.errors import register_exception_handlers
from starmap.app.web.routes import router
from starmap.app.web.session import SidMiddleware
from starmap.app.web.store import EvaluationStore
from starmap.assist.store import ArticulationStore
from starmap.common.clock import SystemClock
from starmap.common.ids import UuidIdGenerator
from starmap.common.sqlite import SqliteDatabase
from starmap.retrieval.index import CourseIndex
from starmap.transfer.costs import load_cost_table


def create_app(config: AppConfig) -> FastAPI:
    for artifact in (config.articulation_db, config.corpus_db):
        if not artifact.exists():
            raise FileNotFoundError(
                f"committed artifact {artifact} does not exist (run `make unpack-data`)"
            )

    app = FastAPI(title="Foothold", openapi_url=None, docs_url=None, redoc_url=None)

    # 1. app.state: every service the routes read, constructed once.
    config.sessions_db.parent.mkdir(parents=True, exist_ok=True)
    app.state.config = config
    app.state.articulation = ArticulationStore(SqliteDatabase(config.articulation_db))
    app.state.index = CourseIndex(SqliteDatabase(config.corpus_db))
    # A missing cost table means dollar fields stay None, the honest
    # "we do not know" (never zero); an invalid one fails loudly here.
    app.state.costs = load_cost_table(config.costs_path) if config.costs_path.exists() else None
    app.state.evaluations = EvaluationStore(SqliteDatabase(config.sessions_db))
    app.state.ids = UuidIdGenerator()
    app.state.clock = SystemClock()
    app.state.bundles = {}

    # 2. Session middleware.
    app.add_middleware(SidMiddleware, ids=app.state.ids, secure=config.secure_cookies)

    # 3. Health probe; accepts HEAD alongside GET.
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    app.add_api_route("/healthz", healthz, methods=["GET", "HEAD"])

    # 4. Exception handlers, most-specific first.
    register_exception_handlers(app)

    # 5. The API router.
    app.include_router(router)

    # 6. LAST: the SPA mount, only when a build exists.
    _mount_spa(app, config.dist_dir)
    return app


def _mount_spa(app: FastAPI, dist_dir: Path) -> None:
    index_path = dist_dir / "index.html"
    if not index_path.exists():
        return
    dist_root = dist_dir.resolve()
    assets_dir = dist_root / "assets"
    if assets_dir.is_dir():
        # Hashed bundles: names change per build, so no cache header needed.
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # Every HTML document carries no-cache (TR 4.4's recorded production
    # incident: browsers cached the SPA shell over a later real page).
    async def spa(path: str) -> FileResponse:
        candidate = (dist_root / path).resolve()
        if candidate.parent == dist_root and candidate.is_file():
            return FileResponse(candidate, headers={"Cache-Control": "no-cache"})
        return FileResponse(dist_root / "index.html", headers={"Cache-Control": "no-cache"})

    app.add_api_route("/{path:path}", spa, methods=["GET", "HEAD"], include_in_schema=False)


def __getattr__(name: str) -> Any:
    if name == "dev_app":
        return create_app(load_config())
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
