import asyncio
from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient, Response

from src.core.config import Settings, get_settings
from src.main import app


@pytest.fixture(autouse=True)
def clear_overrides() -> Iterator[None]:
    yield
    app.dependency_overrides.clear()


def get_health() -> Response:
    async def request_health() -> Response:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get("/api/health")

    return asyncio.run(request_health())


def test_health() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)

    response = get_health()

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "dev", "commit": "unknown"}


def test_health_reports_build_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_VERSION", "1.2.3")
    monkeypatch.setenv("APP_COMMIT", "0594e726f01c70d89ae193a05fc8fda2417acd86")
    app.dependency_overrides[get_settings] = lambda: Settings(_env_file=None)

    response = get_health()

    assert response.json() == {
        "status": "ok",
        "version": "1.2.3",
        "commit": "0594e726f01c70d89ae193a05fc8fda2417acd86",
    }
