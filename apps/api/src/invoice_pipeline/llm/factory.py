import structlog
from httpx import AsyncClient, ConnectError, TimeoutException

from invoice_pipeline.config import LLMProviderName, settings
from invoice_pipeline.llm.base import LLMProvider, NoLLMProviderConfigured

log = structlog.get_logger()

_provider_instance: LLMProvider | None = None


async def _lm_studio_reachable() -> bool:
    try:
        async with AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.LM_STUDIO_BASE_URL}/models")
            return resp.status_code == 200
    except (ConnectError, TimeoutException, Exception):
        return False


async def _llamacpp_reachable() -> bool:
    try:
        async with AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.LLAMACPP_BASE_URL.rstrip('/')}/models")
            return resp.status_code == 200
    except (ConnectError, TimeoutException, Exception):
        return False


async def _ollama_reachable() -> bool:
    try:
        async with AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL.rstrip('/')}/models")
            return resp.status_code == 200
    except (ConnectError, TimeoutException, Exception):
        return False


async def create_provider() -> LLMProvider:
    """Auto-detect and return the best available LLM provider."""
    name = settings.LLM_PROVIDER

    if name == LLMProviderName.LM_STUDIO:
        return _build(LLMProviderName.LM_STUDIO)

    if name == LLMProviderName.OLLAMA:
        return _build(LLMProviderName.OLLAMA)

    if name == LLMProviderName.OPENAI:
        return _build(LLMProviderName.OPENAI)

    if name == LLMProviderName.ANTHROPIC:
        return _build(LLMProviderName.ANTHROPIC)

    if name == LLMProviderName.GEMINI:
        return _build(LLMProviderName.GEMINI)

    if name == LLMProviderName.LLAMACPP:
        return _build(LLMProviderName.LLAMACPP)

    # AUTO detection
    if await _lm_studio_reachable():
        return _build(LLMProviderName.LM_STUDIO)

    if await _ollama_reachable():
        return _build(LLMProviderName.OLLAMA)

    if await _llamacpp_reachable():
        return _build(LLMProviderName.LLAMACPP)

    if settings.ANTHROPIC_API_KEY:
        return _build(LLMProviderName.ANTHROPIC)

    if settings.OPENAI_API_KEY:
        return _build(LLMProviderName.OPENAI)

    if settings.GEMINI_API_KEY:
        return _build(LLMProviderName.GEMINI)

    raise NoLLMProviderConfigured()


def _build(name: LLMProviderName) -> LLMProvider:
    if name == LLMProviderName.LM_STUDIO:
        from invoice_pipeline.llm.lm_studio import LMStudioProvider

        log.info(
            "startup",
            message=f"LLM provider: lm_studio (model={settings.LM_STUDIO_MODEL}, endpoint={settings.LM_STUDIO_BASE_URL})",
        )
        return LMStudioProvider()

    if name == LLMProviderName.OPENAI:
        from invoice_pipeline.llm.openai_client import OpenAIProvider

        log.info("startup", message=f"LLM provider: openai (model={settings.OPENAI_MODEL})")
        return OpenAIProvider()

    if name == LLMProviderName.ANTHROPIC:
        from invoice_pipeline.llm.anthropic_client import AnthropicProvider

        log.info("startup", message=f"LLM provider: anthropic (model={settings.ANTHROPIC_MODEL})")
        return AnthropicProvider()

    if name == LLMProviderName.GEMINI:
        from invoice_pipeline.llm.gemini_client import GeminiProvider

        log.info("startup", message=f"LLM provider: gemini (model={settings.GEMINI_MODEL})")
        return GeminiProvider()

    if name == LLMProviderName.LLAMACPP:
        from invoice_pipeline.llm.llamacpp_client import LlamaCppProvider

        log.info(
            "startup",
            message=f"LLM provider: llamacpp (model={settings.LLAMACPP_MODEL}, endpoint={settings.LLAMACPP_BASE_URL})",
        )
        return LlamaCppProvider()

    if name == LLMProviderName.OLLAMA:
        from invoice_pipeline.llm.ollama_client import OllamaProvider

        log.info(
            "startup",
            message=f"LLM provider: ollama (model={settings.OLLAMA_MODEL}, endpoint={settings.OLLAMA_BASE_URL})",
        )
        return OllamaProvider()

    raise NoLLMProviderConfigured()


async def get_provider() -> LLMProvider:
    """Return the cached provider, initializing on first call."""
    global _provider_instance
    if _provider_instance is None:
        _provider_instance = await create_provider()
    return _provider_instance
