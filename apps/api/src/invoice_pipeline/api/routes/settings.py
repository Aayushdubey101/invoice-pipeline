from typing import Any

from fastapi import APIRouter, HTTPException, Request
from httpx import AsyncClient
from pydantic import BaseModel

from invoice_pipeline.api.limiter import limiter
from invoice_pipeline.config import (
    LLMProviderName,
    save_runtime_overrides,
    settings,
)
from invoice_pipeline.llm.base import NoLLMProviderConfigured

router = APIRouter()


class SettingsUpdate(BaseModel):
    llm_provider: str | None = None
    lm_studio_model: str | None = None
    lm_studio_base_url: str | None = None
    llamacpp_base_url: str | None = None
    llamacpp_model: str | None = None
    llamacpp_api_key: str | None = None
    llamacpp_context_length: int | None = None
    llamacpp_temperature: float | None = None
    llamacpp_max_tokens: int | None = None
    ollama_base_url: str | None = None
    ollama_model: str | None = None


@router.get("/ollama-models")
async def get_ollama_models(base_url: str | None = None) -> dict[str, Any]:
    url = base_url or settings.OLLAMA_BASE_URL
    try:
        async with AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{url.rstrip('/')}/models")
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                models = [m["id"] for m in data]
                return {"online": True, "models": models}
    except Exception as e:
        return {"online": False, "models": [], "error": str(e)}
    return {"online": False, "models": []}


@router.get("/lm-studio-models")
async def get_lm_studio_models(base_url: str | None = None) -> dict[str, Any]:
    url = base_url or settings.LM_STUDIO_BASE_URL
    try:
        async with AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{url.rstrip('/')}/models")
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                models = [m["id"] for m in data]
                return {"online": True, "models": models}
    except Exception as e:
        return {"online": False, "models": [], "error": str(e)}
    return {"online": False, "models": []}


@router.get("/llamacpp/health")
async def llamacpp_health(base_url: str | None = None) -> dict[str, Any]:
    from invoice_pipeline.llm.llamacpp_client import health_check

    return await health_check(base_url)


@router.get("/llamacpp/models")
async def llamacpp_models(base_url: str | None = None) -> dict[str, Any]:
    from invoice_pipeline.llm.llamacpp_client import list_models

    return await list_models(base_url)


@router.post("/test-connection")
@limiter.limit("20/minute")
async def test_connection(
    request: Request,
    provider: str,
    base_url: str | None = None,
) -> dict[str, Any]:
    """Live-check a *local* provider (ollama/lm_studio/llamacpp) using either
    the value passed in (unsaved draft) or the currently effective settings
    value if none is given.

    Phase 13: cloud providers (openai/anthropic/gemini/groq) moved to
    POST /providers/test — a browser-session key is never sent to or checked
    against this backend-config route. This route stays for local providers
    only, which already have dedicated endpoints too but keep this one for
    existing callers.
    """
    if provider == "ollama":
        return await get_ollama_models(base_url)
    if provider == "lm_studio":
        return await get_lm_studio_models(base_url)
    if provider == "llamacpp":
        from invoice_pipeline.llm.llamacpp_client import health_check

        result = await health_check(base_url)
        return {"online": result.get("online", False), **result}

    raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")


@router.get("/")
@router.get("", include_in_schema=False)
async def get_settings() -> dict[str, Any]:
    return {
        "llm_provider": settings.LLM_PROVIDER.value,
        "lm_studio_model": settings.LM_STUDIO_MODEL,
        "lm_studio_base_url": settings.LM_STUDIO_BASE_URL,
        "llamacpp_base_url": settings.LLAMACPP_BASE_URL,
        "llamacpp_model": settings.LLAMACPP_MODEL,
        "has_llamacpp_key": bool(
            settings.LLAMACPP_API_KEY and settings.LLAMACPP_API_KEY != "not-needed"
        ),
        "llamacpp_context_length": settings.LLAMACPP_CONTEXT_LENGTH,
        "llamacpp_temperature": settings.LLAMACPP_TEMPERATURE,
        "llamacpp_max_tokens": settings.LLAMACPP_MAX_TOKENS,
        "ollama_base_url": settings.OLLAMA_BASE_URL,
        "ollama_model": settings.OLLAMA_MODEL,
    }


@router.patch("/")
@router.patch("", include_in_schema=False)
@limiter.limit("10/minute")
async def update_settings(request: Request, body: SettingsUpdate) -> dict[str, Any]:
    if body.llm_provider is not None:
        try:
            settings.LLM_PROVIDER = LLMProviderName(body.llm_provider)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid provider: {body.llm_provider}")

    if body.lm_studio_model is not None:
        settings.LM_STUDIO_MODEL = body.lm_studio_model
    if body.lm_studio_base_url is not None:
        settings.LM_STUDIO_BASE_URL = body.lm_studio_base_url

    if body.llamacpp_base_url is not None:
        settings.LLAMACPP_BASE_URL = body.llamacpp_base_url
    if body.llamacpp_model is not None:
        settings.LLAMACPP_MODEL = body.llamacpp_model
    if body.llamacpp_api_key:
        settings.LLAMACPP_API_KEY = body.llamacpp_api_key
    if body.llamacpp_context_length is not None:
        settings.LLAMACPP_CONTEXT_LENGTH = body.llamacpp_context_length
    if body.llamacpp_temperature is not None:
        settings.LLAMACPP_TEMPERATURE = body.llamacpp_temperature
    if body.llamacpp_max_tokens is not None:
        settings.LLAMACPP_MAX_TOKENS = body.llamacpp_max_tokens

    if body.ollama_base_url is not None:
        settings.OLLAMA_BASE_URL = body.ollama_base_url
    if body.ollama_model is not None:
        settings.OLLAMA_MODEL = body.ollama_model

    # Persist to disk so changes survive restart.
    try:
        save_runtime_overrides(settings)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to persist settings: {exc}")

    # Reset cached provider so the next request rebuilds with new values.
    from invoice_pipeline.llm import factory

    factory._provider_instance = None

    # Eagerly rebuild to surface configuration errors immediately + warm cache.
    try:
        factory._provider_instance = await factory.create_provider()
    except NoLLMProviderConfigured as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Provider init failed: {exc}")

    return await get_settings()
