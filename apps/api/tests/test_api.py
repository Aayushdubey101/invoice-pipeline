import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


@pytest.mark.asyncio
async def test_docs_available(client: AsyncClient) -> None:
    response = await client.get("/openapi.json")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_llm_status(client: AsyncClient) -> None:
    response = await client.get("/llm/status")
    assert response.status_code == 200
