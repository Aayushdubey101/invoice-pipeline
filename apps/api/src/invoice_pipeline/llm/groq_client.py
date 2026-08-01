"""Groq provider (OpenAI-compatible hosted API, https://api.groq.com/openai/v1)."""

import time

import instructor
import structlog
from openai import AsyncOpenAI
from pydantic import BaseModel

from invoice_pipeline.config import settings
from invoice_pipeline.llm.base import ExtractionMeta, NoLLMProviderConfigured

log = structlog.get_logger()


class GroqProvider:
    provider_name = "groq"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        config: dict | None = None,
    ) -> None:
        resolved_key = api_key or settings.GROQ_API_KEY
        if not resolved_key:
            raise NoLLMProviderConfigured("GROQ_API_KEY is not set.")
        self._base_url = settings.GROQ_BASE_URL.rstrip("/")
        self._model = model or settings.GROQ_MODEL
        self._config = config or {}
        # Mode.JSON (plain JSON response, validated client-side by pydantic) instead of
        # the default tool-calling mode: Groq's tool-call validation rejects function
        # calls that omit optional/nullable schema properties, which real extractions
        # routinely do (e.g. a missing buyer_address) — stricter than OpenAI's.
        self._client = instructor.from_openai(
            AsyncOpenAI(
                api_key=resolved_key,
                base_url=self._base_url,
                timeout=settings.GROQ_TIMEOUT,
            ),
            mode=instructor.Mode.JSON,
        )

    async def extract(
        self,
        text: str,
        schema: type[BaseModel],
        system_prompt: str,
        temperature: float = 0.0,
    ) -> tuple[BaseModel, ExtractionMeta]:
        start = time.monotonic()
        effective_temp = self._config.get(
            "temperature", temperature if temperature is not None else settings.GROQ_TEMPERATURE
        )

        response, raw = await self._client.chat.completions.create_with_completion(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            response_model=schema,
            temperature=effective_temp,
            max_tokens=self._config.get("max_tokens", settings.GROQ_MAX_TOKENS),
            max_retries=settings.LLM_MAX_RETRIES,
        )

        latency_ms = (time.monotonic() - start) * 1000
        usage = raw.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        meta = ExtractionMeta(
            provider_name=self.provider_name,
            model_name=self._model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_estimate=0.0,  # Groq pricing varies by model; not tracked here.
        )

        log.info(
            "llm_extraction",
            provider=self.provider_name,
            model=self._model,
            latency_ms=round(latency_ms),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

        return response, meta
