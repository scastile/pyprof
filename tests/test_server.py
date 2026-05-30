"""Tests for the FastAPI server."""

import pytest
from httpx import ASGITransport, AsyncClient

from pyprof.profiler import profile_function
from pyprof.server import app, save_data


@pytest.fixture
def sample_data():
    return profile_function(lambda: sum(range(1000)))


@pytest.fixture
def transport():
    return ASGITransport(app=app)


@pytest.mark.anyio
async def test_health(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


@pytest.mark.anyio
async def test_data_endpoint(transport, sample_data):
    save_data(sample_data)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/data")
        assert resp.status_code == 200
        data = resp.json()
        assert "command" in data
        assert "functions" in data
        assert "flame_tree" in data
        assert len(data["functions"]) > 0


@pytest.mark.anyio
async def test_functions_endpoint(transport, sample_data):
    save_data(sample_data)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/functions?sort=time&limit=10")
        assert resp.status_code == 200
        funcs = resp.json()
        assert isinstance(funcs, list)
        assert len(funcs) <= 10


@pytest.mark.anyio
async def test_index(transport):
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/")
        assert resp.status_code == 200
        assert "pyprof" in resp.text.lower() or "flame" in resp.text.lower()
