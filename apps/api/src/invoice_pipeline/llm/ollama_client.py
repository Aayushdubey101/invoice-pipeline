"""Ollama provider (OpenAI-compatible local server at localhost:11434)."""

from invoice_pipeline.config import settings
from invoice_pipeline.llm.llamacpp_client import LlamaCppProvider


class OllamaProvider(LlamaCppProvider):
    provider_name = "ollama"

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.OLLAMA_BASE_URL,
            model=settings.OLLAMA_MODEL,
            api_key="ollama",
        )
