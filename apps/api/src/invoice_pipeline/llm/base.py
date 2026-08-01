from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from pydantic import BaseModel


@dataclass
class ExtractionMeta:
    provider_name: str
    model_name: str
    latency_ms: float
    tokens_in: int
    tokens_out: int
    cost_estimate: float


@runtime_checkable
class LLMProvider(Protocol):
    async def extract(
        self,
        text: str,
        schema: type[BaseModel],
        system_prompt: str,
        temperature: float = 0.0,
    ) -> tuple[BaseModel, ExtractionMeta]: ...


class NoLLMProviderConfigured(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or (
                "No LLM provider configured. Set LLM_PROVIDER env var to one of: "
                "auto, lm_studio, ollama, llamacpp, openai, anthropic, gemini, groq. "
                "Or set ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY / GROQ_API_KEY "
                "for auto-detection. Or start LM Studio at http://localhost:1234."
            )
        )
