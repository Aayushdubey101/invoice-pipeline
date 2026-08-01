"""Phase 13 BYOK — POST /providers/test never persists or echoes the key."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from invoice_pipeline.api.main import app


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_provider_test_success(client: AsyncClient) -> None:
    with (
        patch("invoice_pipeline.api.routes.providers.create_provider", new_callable=AsyncMock),
        patch(
            "invoice_pipeline.api.routes.providers.test_openai_compatible",
            new_callable=AsyncMock,
            return_value={"online": True, "models": ["gpt-4o-mini"]},
        ),
    ):
        res = await client.post(
            "/providers/test",
            json={
                "provider": "openai",
                "api_key": "sk-super-secret-value",
                "model": "gpt-4o-mini",
            },
        )

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["error"] is None
    assert isinstance(data["latency_ms"], float)
    assert "sk-super-secret-value" not in res.text


@pytest.mark.asyncio
async def test_provider_test_invalid_api_key(client: AsyncClient) -> None:
    class FakeAuthError(Exception):
        status_code = 401

    with patch(
        "invoice_pipeline.api.routes.providers.create_provider",
        new_callable=AsyncMock,
        side_effect=FakeAuthError("bad key"),
    ):
        res = await client.post(
            "/providers/test",
            json={"provider": "anthropic", "api_key": "sk-ant-bad-secret", "model": "claude-x"},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert data["error"] == "Invalid API key"
    assert "sk-ant-bad-secret" not in res.text


@pytest.mark.asyncio
async def test_provider_test_gemini_check_reports_offline(client: AsyncClient) -> None:
    """Covers the non-exception failure path: the live-check helper itself
    returns {"online": False, "error": ...} instead of raising."""
    with (
        patch("invoice_pipeline.api.routes.providers.create_provider", new_callable=AsyncMock),
        patch(
            "invoice_pipeline.api.routes.providers.test_gemini",
            new_callable=AsyncMock,
            return_value={"online": False, "error": "Model not found"},
        ),
    ):
        res = await client.post(
            "/providers/test",
            json={"provider": "gemini", "api_key": "AIza-secret-value", "model": "gemini-x"},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert data["error"] == "Model not found"
    assert "AIza-secret-value" not in res.text


@pytest.mark.asyncio
async def test_provider_test_rate_limited(client: AsyncClient) -> None:
    class FakeRateLimitError(Exception):
        status_code = 429

    with patch(
        "invoice_pipeline.api.routes.providers.create_provider",
        new_callable=AsyncMock,
        side_effect=FakeRateLimitError("slow down"),
    ):
        res = await client.post(
            "/providers/test",
            json={"provider": "groq", "api_key": "gsk-bad-secret", "model": "llama-3.3"},
        )

    assert res.status_code == 200
    data = res.json()
    assert data["success"] is False
    assert data["error"] == "Rate limited"
    assert "gsk-bad-secret" not in res.text
