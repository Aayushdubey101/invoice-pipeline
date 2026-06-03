from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from invoice_pipeline.api.main import app


@pytest.fixture
async def settings_client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_get_settings(settings_client: AsyncClient) -> None:
    res = await settings_client.get("/settings/")
    assert res.status_code == 200
    data = res.json()
    assert "llm_provider" in data
    assert "lm_studio_model" in data
    assert "openai_model" in data


@pytest.mark.asyncio
async def test_get_ollama_models_online(settings_client: AsyncClient) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "gemma:2b"}, {"id": "llama3"}]}

    with patch("invoice_pipeline.api.routes.settings.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        res = await settings_client.get("/settings/ollama-models?base_url=http://local:11434")

    assert res.status_code == 200
    data = res.json()
    assert data["online"] is True
    assert "gemma:2b" in data["models"]
    assert "llama3" in data["models"]


@pytest.mark.asyncio
async def test_get_ollama_models_offline(settings_client: AsyncClient) -> None:
    with patch("invoice_pipeline.api.routes.settings.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        res = await settings_client.get("/settings/ollama-models")

    assert res.status_code == 200
    data = res.json()
    assert data["online"] is False
    assert data["error"] == "Connection refused"


@pytest.mark.asyncio
async def test_get_lm_studio_models_online(settings_client: AsyncClient) -> None:
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"data": [{"id": "qwen"}, {"id": "llama"}]}

    with patch("invoice_pipeline.api.routes.settings.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        res = await settings_client.get("/settings/lm-studio-models?base_url=http://local:1234")

    assert res.status_code == 200
    data = res.json()
    assert data["online"] is True
    assert "qwen" in data["models"]


@pytest.mark.asyncio
async def test_get_lm_studio_models_offline(settings_client: AsyncClient) -> None:
    with patch("invoice_pipeline.api.routes.settings.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=Exception("Unreachable"))
        mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        res = await settings_client.get("/settings/lm-studio-models")

    assert res.status_code == 200
    data = res.json()
    assert data["online"] is False
    assert data["error"] == "Unreachable"


@pytest.mark.asyncio
async def test_llamacpp_health_online(settings_client: AsyncClient) -> None:
    health_val = {
        "online": True,
        "latency_ms": 15.0,
        "endpoint": "http://local/health",
        "body": "ok",
    }
    with patch(
        "invoice_pipeline.llm.llamacpp_client.health_check",
        new_callable=AsyncMock,
        return_value=health_val,
    ):
        res = await settings_client.get("/settings/llamacpp/health")

    assert res.status_code == 200
    data = res.json()
    assert data["online"] is True
    assert data["latency_ms"] == 15.0


@pytest.mark.asyncio
async def test_llamacpp_models_online(settings_client: AsyncClient) -> None:
    models_val = {"online": True, "models": ["local-model-1"]}
    with patch(
        "invoice_pipeline.llm.llamacpp_client.list_models",
        new_callable=AsyncMock,
        return_value=models_val,
    ):
        res = await settings_client.get("/settings/llamacpp/models")

    assert res.status_code == 200
    data = res.json()
    assert data["online"] is True
    assert "local-model-1" in data["models"]


@pytest.mark.asyncio
async def test_update_settings_success(settings_client: AsyncClient) -> None:
    mock_provider = MagicMock()
    mock_provider.provider_name = "openai"
    mock_provider._model = "gpt-4o"

    with (
        patch("invoice_pipeline.api.routes.settings.save_runtime_overrides") as mock_save,
        patch(
            "invoice_pipeline.llm.factory.create_provider",
            new_callable=AsyncMock,
            return_value=mock_provider,
        ),
    ):
        res = await settings_client.patch(
            "/settings/",
            json={
                "llm_provider": "openai",
                "openai_model": "gpt-4o",
                "openai_api_key": "test-key-123",
                "lm_studio_model": "qwen2",
                "lm_studio_base_url": "http://other:1234",
                "ollama_base_url": "http://other:11434",
                "ollama_model": "llama3:8b",
                "llamacpp_base_url": "http://other:8080",
                "llamacpp_model": "llama-local",
                "llamacpp_api_key": "local-key",
                "llamacpp_context_length": 2048,
                "llamacpp_temperature": 0.5,
                "llamacpp_max_tokens": 1024,
            },
        )

    assert res.status_code == 200
    mock_save.assert_called_once()
    data = res.json()
    assert data["llm_provider"] == "openai"
    assert data["openai_model"] == "gpt-4o"
    assert data["has_openai_key"] is True


@pytest.mark.asyncio
async def test_update_settings_invalid_provider(settings_client: AsyncClient) -> None:
    res = await settings_client.patch("/settings/", json={"llm_provider": "invalid-provider-name"})
    assert res.status_code == 400
    assert "Invalid provider" in res.json()["detail"]
