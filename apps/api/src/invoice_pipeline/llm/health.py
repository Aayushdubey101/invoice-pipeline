"""Live-checks the platform's own .env cloud keys before auto-detect picks one.

Without this, `_auto_detect_provider()` picked the first cloud key that was
merely *present* in .env, in fixed priority order — an expired/quota'd key
would get selected and every extraction would fail. This tests reachability
first (result cached briefly, so normal traffic doesn't hammer the provider's
API on every single upload) and lets the caller fall through to the next
configured key. BYOK requests never go through here — a caller's own key is
always used exactly as given.
"""

import time

import structlog

from invoice_pipeline.config import LLMProviderName, settings
from invoice_pipeline.llm.testing import test_anthropic, test_gemini, test_openai_compatible

log = structlog.get_logger()

_CACHE_TTL_SECONDS = 300.0
_cache: dict[LLMProviderName, tuple[bool, float]] = {}


async def _check(name: LLMProviderName, key: str) -> bool:
    if name == LLMProviderName.ANTHROPIC:
        result = await test_anthropic(key)
    elif name == LLMProviderName.GEMINI:
        result = await test_gemini(key)
    elif name == LLMProviderName.GROQ:
        result = await test_openai_compatible(key, settings.GROQ_BASE_URL, "Groq")
    else:
        result = await test_openai_compatible(key, "https://api.openai.com/v1", "OpenAI")
    return bool(result.get("online"))


async def cloud_key_works(name: LLMProviderName, key: str) -> bool:
    """Cached live check — a given key is re-tested at most once per TTL."""
    cached = _cache.get(name)
    now = time.monotonic()
    if cached is not None and now - cached[1] < _CACHE_TTL_SECONDS:
        return cached[0]
    online = await _check(name, key)
    _cache[name] = (online, now)
    if not online:
        log.warning("cloud_key_unhealthy", provider=name.value)
    return online
