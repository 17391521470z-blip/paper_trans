from __future__ import annotations

from typing import Any

import pytest


pytestmark = pytest.mark.asyncio


class TestHealth:
    async def test_health_endpoint(self, client: Any) -> None:
        resp = await client.get("/api/v1/health")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["status"] == "ok"
        assert "version" in data

    async def test_health_returns_json(self, client: Any) -> None:
        resp = await client.get("/api/v1/health")
        assert resp.headers["content-type"].startswith("application/json")

    async def test_openapi_available(self, client: Any) -> None:
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "openapi" in data
        assert "paths" in data

    async def test_root_not_found(self, client: Any) -> None:
        resp = await client.get("/api/v1/nonexistent-route-12345")
        assert resp.status_code in (404,), resp.text
