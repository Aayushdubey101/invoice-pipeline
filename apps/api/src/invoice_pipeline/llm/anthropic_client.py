import time

import anthropic
import instructor
import structlog
from pydantic import BaseModel

from invoice_pipeline.config import settings
from invoice_pipeline.llm.base import ExtractionMeta

log = structlog.get_logger()

_ANTHROPIC_COSTS: dict[str, tuple[float, float]] = {
    "claude-sonnet-4-5": (0.003, 0.015),
    "claude-haiku-4-5-20251001": (0.00025, 0.00125),
    "claude-opus-4-7": (0.015, 0.075),
}


class AnthropicProvider:
    provider_name = "anthropic"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        config: dict | None = None,
    ) -> None:
        self._client = instructor.from_anthropic(
            anthropic.AsyncAnthropic(api_key=api_key or settings.ANTHROPIC_API_KEY)
        )
        self._model = model or settings.ANTHROPIC_MODEL
        self._config = config or {}

    async def extract(
        self,
        text: str,
        schema: type[BaseModel],
        system_prompt: str,
        temperature: float = 0.0,
    ) -> tuple[BaseModel, ExtractionMeta]:
        start = time.monotonic()

        response, raw = await self._client.messages.create_with_completion(
            model=self._model,
            max_tokens=self._config.get("max_tokens", 4096),
            system=system_prompt,
            messages=[{"role": "user", "content": text}],
            response_model=schema,
            temperature=self._config.get("temperature", temperature),
            max_retries=settings.LLM_MAX_RETRIES,
        )

        latency_ms = (time.monotonic() - start) * 1000
        usage = raw.usage
        tokens_in = usage.input_tokens if usage else 0
        tokens_out = usage.output_tokens if usage else 0

        cost_in, cost_out = _ANTHROPIC_COSTS.get(self._model, (0.0, 0.0))
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
