import time

import instructor
import structlog
from openai import AsyncOpenAI
from pydantic import BaseModel

from invoice_pipeline.config import settings
from invoice_pipeline.llm.base import ExtractionMeta

log = structlog.get_logger()

# Cost per 1K tokens (input, output) for common models
_OPENAI_COSTS: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.00015, 0.00060),
    "gpt-4o": (0.00250, 0.01000),
    "gpt-4-turbo": (0.01000, 0.03000),
}


class OpenAIProvider:
    provider_name = "openai"

    def __init__(self) -> None:
        self._client = instructor.from_openai(AsyncOpenAI(api_key=settings.OPENAI_API_KEY))
        self._model = settings.OPENAI_MODEL

    async def extract(
        self,
        text: str,
        schema: type[BaseModel],
        system_prompt: str,
        temperature: float = 0.0,
    ) -> tuple[BaseModel, ExtractionMeta]:
        start = time.monotonic()

        response, raw = await self._client.chat.completions.create_with_completion(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            response_model=schema,
            temperature=temperature,
            max_retries=settings.LLM_MAX_RETRIES,
        )

        latency_ms = (time.monotonic() - start) * 1000
        usage = raw.usage
        tokens_in = usage.prompt_tokens if usage else 0
        tokens_out = usage.completion_tokens if usage else 0

        cost_in, cost_out = _OPENAI_COSTS.get(self._model, (0.0, 0.0))
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
