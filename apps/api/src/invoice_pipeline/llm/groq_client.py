"""Groq provider (OpenAI-compatible hosted API, https://api.groq.com/openai/v1)."""

import time

import instructor
import structlog
from openai import AsyncOpenAI, NotFoundError
from pydantic import BaseModel

from invoice_pipeline.config import settings
from invoice_pipeline.llm.base import ExtractionMeta, NoLLMProviderConfigured

log = structlog.get_logger()

# Groq periodically retires models outright (not just deprecates) - the
# configured GROQ_MODEL 404s with model_not_found/model_decommissioned and
# stays broken until someone edits config by hand (happened today: llama-3.x
# -> openai/gpt-oss-120b, see commit 6eb60aa). Try these, in order, as a
# same-provider fallback before giving up. Keep in sync with active chat
# models at https://console.groq.com/dashboard/limits - skip guard/safety
# and non-English-only models, they don't support this pipeline's JSON mode.
_GROQ_MODEL_CANDIDATES: tuple[str, ...] = (
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
)


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

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
        max_tokens = self._config.get("max_tokens", settings.GROQ_MAX_TOKENS)

        try:
            response, raw = await self._client.chat.completions.create_with_completion(
                model=self._model,
                messages=messages,
                response_model=schema,
                temperature=effective_temp,
                max_tokens=max_tokens,
                max_retries=settings.LLM_MAX_RETRIES,
            )
        except NotFoundError as exc:
            response, raw = await self._retry_with_fallback_model(
                exc, messages, schema, effective_temp, max_tokens
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

    async def _retry_with_fallback_model(
        self,
        original_exc: NotFoundError,
        messages: list[dict],
        schema: type[BaseModel],
        temperature: float,
        max_tokens: int | None,
    ) -> tuple[BaseModel, object]:
        """self._model was retired by Groq (404) — try candidates, adopt first that works."""
        for candidate in _GROQ_MODEL_CANDIDATES:
            if candidate == self._model:
                continue
            log.warning(
                "groq_model_retired",
                old_model=self._model,
                new_model=candidate,
                error=str(original_exc),
            )
            try:
                response, raw = await self._client.chat.completions.create_with_completion(
                    model=candidate,
                    messages=messages,
                    response_model=schema,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    max_retries=settings.LLM_MAX_RETRIES,
                )
            except NotFoundError:
                continue
            self._model = candidate
            return response, raw
        raise original_exc
