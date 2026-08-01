import time

import instructor
import structlog
from google import genai
from pydantic import BaseModel

from invoice_pipeline.config import settings
from invoice_pipeline.llm.base import ExtractionMeta, NoLLMProviderConfigured

log = structlog.get_logger()

_GEMINI_COSTS: dict[str, tuple[float, float]] = {
    "gemini-2.0-flash": (0.000075, 0.000300),
    "gemini-1.5-pro": (0.00125, 0.00500),
}


class GeminiProvider:
    provider_name = "gemini"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        config: dict | None = None,
    ) -> None:
        resolved_key = api_key or settings.GEMINI_API_KEY
        if not resolved_key or not resolved_key.strip():
            raise NoLLMProviderConfigured("Gemini API key is not configured.")
        try:
            google_client = genai.Client(api_key=resolved_key)
            self._client = instructor.from_genai(google_client, use_async=True)
            self._model = model or settings.GEMINI_MODEL
            self._config = config or {}
        except Exception as e:
            raise NoLLMProviderConfigured(f"Failed to initialize Gemini Client: {str(e)}") from e

    async def extract(
        self,
        text: str,
        schema: type[BaseModel],
        system_prompt: str,
        temperature: float = 0.0,
    ) -> tuple[BaseModel, ExtractionMeta]:
        start = time.monotonic()

        extra_kwargs: dict = {}
        if self._config.get("max_tokens") is not None:
            extra_kwargs["max_tokens"] = self._config["max_tokens"]

        response, raw = await self._client.chat.completions.create_with_completion(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            response_model=schema,
            temperature=self._config.get("temperature", temperature),
            max_retries=settings.LLM_MAX_RETRIES,
            **extra_kwargs,
        )

        latency_ms = (time.monotonic() - start) * 1000
        usage = getattr(raw, "usage_metadata", None)
        tokens_in = getattr(usage, "prompt_token_count", 0) or 0
        tokens_out = getattr(usage, "candidates_token_count", 0) or 0

        cost_in, cost_out = _GEMINI_COSTS.get(self._model, (0.0, 0.0))
        cost = (tokens_in / 1000 * cost_in) + (tokens_out / 1000 * cost_out)

        meta = ExtractionMeta(
            provider_name=self.provider_name,
            model_name=self._model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_estimate=cost,
        )

        log.info(
            "llm_extraction",
            provider=self.provider_name,
            model=self._model,
            latency_ms=round(latency_ms),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=round(cost, 6),
        )

        return response, meta
