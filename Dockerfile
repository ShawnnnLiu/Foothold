# syntax=docker/dockerfile:1
# Foothold runtime image (plan "Deployment"): one machine, the committed
# read-only artifacts baked in, sessions.db redirected to the /data volume
# through FOOTHOLD_SESSIONS_DB. The image mirrors the repo layout
# (/app/backend, /app/data, /app/frontend/dist) so every repo-relative
# default in config.py and the build script holds unchanged.

# Stage 1: the SPA build.
FROM node:22-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: the uv-managed backend, same toolchain as local dev.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app/backend
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

# Dependency layer: invalidated only by the lockfile.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
RUN uv sync --frozen --no-dev

# Committed artifacts; articulation.db restores from its gzip exactly as
# `make unpack-data` does on a fresh clone.
COPY data/articulation.db.gz data/corpus.db /app/data/
COPY data/curated/ /app/data/curated/
RUN uv run --no-sync python scripts/build_articulation.py --unpack

COPY --from=frontend /app/frontend/dist /app/frontend/dist

# Fly terminates TLS, so cookies are Secure; the sessions database lives on
# the mounted volume, the only writable path that survives a redeploy.
ENV FOOTHOLD_SESSIONS_DB=/data/sessions.db \
    FOOTHOLD_SECURE_COOKIES=1

EXPOSE 8000
# One process by design: the four session stores share one SQLite connection,
# and background jobs run in-process. Never add workers here.
CMD ["uv", "run", "--no-sync", "uvicorn", "starmap.app.web.app:dev_app", "--host", "0.0.0.0", "--port", "8000"]
