"""Live provider connectivity checks + error classification.

Relocated from api/routes/settings.py (Phase 13 BYOK) — the only remaining
caller is POST /providers/test, which live-checks a browser-supplied cloud
API key before the frontend saves it for the session. Never log or persist
the api_key values passed in here.
"""

from typing import Any

import structlog

log = structlog.get_logger()


async def test_openai_compatible(api_key: str, base_url: str, label: str) -> dict[str, Any]:
    from openai import AsyncOpenAI

    if not api_key:
        return {"online": False, "error": f"{label} API key is not configured."}
    try:
        client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=5.0)
        page = await client.models.list()
        models = [m.id for m in page.data][:20]
        return {"online": True, "models": models}
    except Exception as e:
        return {"online": False, "error": classify_error(e)}


async def test_anthropic(api_key: str) -> dict[str, Any]:
    import anthropic

    if not api_key:
        return {"online": False, "error": "Anthropic API key is not configured."}
    try:
        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=5.0)
        page = await client.models.list(limit=20)
        models = [m.id for m in page.data]
        return {"online": True, "models": models}
    except Exception as e:
        return {"online": False, "error": classify_error(e)}


async def test_gemini(api_key: str) -> dict[str, Any]:
    from google import genai

    if not api_key:
        return {"online": False, "error": "Gemini API key is not configured."}
    try:
        client = genai.Client(api_key=api_key)
        models = []
        async for m in await client.aio.models.list():
            models.append(m.name)
            if len(models) >= 20:
                break
        return {"online": True, "models": models}
    except Exception as e:
        return {"online": False, "error": classify_error(e)}


def classify_error(exc: Exception) -> str:
    """Map a provider SDK exception to a short user-facing string.

    openai/anthropic SDKs expose `status_code` directly on their APIStatusError
    subclasses; google-genai exposes an int `code` instead. Read both
    defensively rather than importing every SDK's exception hierarchy — good
    enough for a user-facing hint, not meant to be exhaustive.
    """
    status_code = getattr(exc, "status_code", None)
    if not isinstance(status_code, int):
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
    if not isinstance(status_code, int):
        code = getattr(exc, "code", None)
        status_code = code if isinstance(code, int) else None

    if status_code == 401:
        return "Invalid API key"
    if status_code == 404:
        return "Model not found"
    if status_code == 429:
        return "Quota exceeded" if "quota" in str(exc).lower() else "Rate limited"

    if "timeout" in type(exc).__name__.lower() or "timed out" in str(exc).lower():
        return "Network timeout"

    return str(exc)
