"""Phase 13 BYOK — live-check a browser-session cloud provider key.

POST /providers/test never touches disk/DB: it builds a provider straight
from the request body via llm.factory.create_provider(override=...) and
runs one lightweight live call. Never log or return the api_key/config.
"""

import time
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Request
from pydantic import BaseModel

from invoice_pipeline.api.limiter import limiter
from invoice_pipeline.config import settings
from invoice_pipeline.llm.factory import create_provider
from invoice_pipeline.llm.override import ProviderOverride
from invoice_pipeline.llm.testing import (
    classify_error,
    test_anthropic,
    test_gemini,
    test_openai_compatible,
)

log = structlog.get_logger()
router = APIRouter()


class ProviderTestRequest(BaseModel):
    provider: Literal["openai", "anthropic", "gemini", "groq"]
    api_key: str
    model: str
    config: dict[str, Any] | None = None


class ProviderTestResponse(BaseModel):
    success: bool
    latency_ms: float
    error: str | None = None


@router.post("/test", response_model=ProviderTestResponse)
@limiter.limit("10/minute")
async def test_provider(request: Request, body: ProviderTestRequest) -> ProviderTestResponse:
    override = ProviderOverride(
        provider=body.provider, api_key=body.api_key, model=body.model, config=body.config or {}
    )
    start = time.monotonic()
    try:
        # Constructs the provider client directly from the override — surfaces
        # config errors (e.g. an empty Gemini key) before the live check runs.
        await create_provider(override=override)

        if override.provider == "openai":
            check = await test_openai_compatible(
                override.api_key, "https://api.openai.com/v1", "OpenAI"
            )
        elif override.provider == "groq":
            check = await test_openai_compatible(override.api_key, settings.GROQ_BASE_URL, "Groq")
        elif override.provider == "anthropic":
            check = await test_anthropic(override.api_key)
        else:
            check = await test_gemini(override.api_key)

        latency_ms = (time.monotonic() - start) * 1000
        if not check.get("online"):
            error = check.get("error") or "Connection failed"
            log.info("provider_test_failed", provider=override.provider, error=error)
            return ProviderTestResponse(success=False, latency_ms=latency_ms, error=error)

        return ProviderTestResponse(success=True, latency_ms=latency_ms, error=None)
    except Exception as exc:
        latency_ms = (time.monotonic() - start) * 1000
        error = classify_error(exc)
        log.info("provider_test_failed", provider=override.provider, error=error)
        return ProviderTestResponse(success=False, latency_ms=latency_ms, error=error)
