"""Assembly-order behavior (doc 01 test 1): health probe, JSON 404s, and the
SPA catch-all mounting last, only when a build exists, confined to dist."""

from pathlib import Path

from fastapi.testclient import TestClient

from starmap.app.web.app import create_app
from starmap.app.web.config import AppConfig
from tests.app.conftest import build_app_config

INDEX_HTML = "<!doctype html><title>Foothold</title>"


def test_healthz_answers_get(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_healthz_answers_head(client: TestClient) -> None:
    response = client.head("/healthz")
    assert response.status_code == 200
    assert response.content == b""


def test_unknown_api_path_is_a_json_404(client: TestClient) -> None:
    response = client.get("/api/nope")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")


def test_without_a_dist_build_non_api_paths_404(client: TestClient) -> None:
    assert client.get("/").status_code == 404
    assert client.get("/anything").status_code == 404


def _dist_config(tmp_path: Path) -> AppConfig:
    config = build_app_config(tmp_path)
    config.dist_dir.mkdir()
    (config.dist_dir / "index.html").write_text(INDEX_HTML, encoding="utf-8")
    return config


def test_with_a_build_the_catch_all_serves_index_with_no_cache(tmp_path: Path) -> None:
    client = TestClient(create_app(_dist_config(tmp_path)))
    for path in ("/", "/some/spa/route"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == INDEX_HTML
        assert response.headers["cache-control"] == "no-cache"


def test_the_catch_all_serves_a_real_top_level_file(tmp_path: Path) -> None:
    config = _dist_config(tmp_path)
    (config.dist_dir / "robots.txt").write_text("User-agent: *\n", encoding="utf-8")
    client = TestClient(create_app(config))
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert response.text == "User-agent: *\n"


def test_a_traversal_attempt_stays_confined_to_dist(tmp_path: Path) -> None:
    config = _dist_config(tmp_path)
    (tmp_path / "secret.txt").write_text("out of bounds", encoding="utf-8")
    client = TestClient(create_app(config))
    response = client.get("/%2e%2e/secret.txt")
    assert response.status_code == 200
    assert response.text == INDEX_HTML


def test_api_routes_stay_reachable_ahead_of_the_catch_all(tmp_path: Path) -> None:
    client = TestClient(create_app(_dist_config(tmp_path)))
    response = client.get("/api/institutions", params={"kind": "cc"})
    assert response.status_code == 200
    assert "institutions" in response.json()


def test_create_app_fails_eagerly_on_a_missing_artifact(tmp_path: Path) -> None:
    config = build_app_config(tmp_path)
    config.articulation_db.unlink()
    try:
        create_app(config)
    except FileNotFoundError as error:
        assert "articulation.db" in str(error)
    else:
        raise AssertionError("create_app opened a missing artifact without failing")
