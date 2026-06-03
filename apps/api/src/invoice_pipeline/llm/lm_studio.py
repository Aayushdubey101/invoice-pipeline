import json
import re
import time
from typing import Any

import structlog
from httpx import AsyncClient
from openai import AsyncOpenAI
from pydantic import BaseModel

from invoice_pipeline.config import settings
from invoice_pipeline.llm.base import ExtractionMeta

log = structlog.get_logger()

_TOP_LEVEL_FIELD_VALUE_KEYS = frozenset(
    {
        "invoice_number",
        "invoice_date",
        "due_date",
        "vendor_name",
        "vendor_address",
        "vendor_tax_id",
        "buyer_name",
        "buyer_address",
        "subtotal",
        "tax_amount",
        "total_amount",
        "currency",
        "payment_terms",
        "purchase_order",
    }
)
_LINE_ITEM_KEYS = frozenset({"description", "quantity", "unit_price", "total"})


def _to_field_value(val: object) -> dict[str, Any]:
    if val is None:
        return {"value": None, "confidence": 0.0, "evidence": None}
    if isinstance(val, str):
        return {"value": val, "confidence": 1.0, "evidence": None}
    return val  # type: ignore[return-value]


def _normalize_invoice_json(raw: dict[str, Any]) -> dict[str, Any]:
    """Coerce flat strings / nulls to FieldValue objects so pydantic validation passes."""
    result = {**raw}
    for key in _TOP_LEVEL_FIELD_VALUE_KEYS:
        if key in result and not isinstance(result[key], dict):
            result[key] = _to_field_value(result[key])
    if isinstance(result.get("line_items"), list):
        items = []
        for item in result["line_items"]:
            if isinstance(item, dict):
                item = {
                    **item,
                    **{
                        k: _to_field_value(item[k])
                        for k in _LINE_ITEM_KEYS
                        if k in item and not isinstance(item[k], dict)
                    },
                }
            items.append(item)
        result["line_items"] = items
    return result


async def _get_active_models() -> list[str]:
    """Return list of active model IDs from LM Studio."""
    try:
        async with AsyncClient(timeout=2.0) as client:
            resp = await client.get(f"{settings.LM_STUDIO_BASE_URL}/models")
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                return [m["id"] for m in data]
    except Exception:
        pass
    return []


class LMStudioProvider:
    provider_name = "lm_studio"

    def __init__(self) -> None:
        self._openai_client = AsyncOpenAI(
            base_url=settings.LM_STUDIO_BASE_URL,
            api_key="not-needed",
        )
        self._model: str | None = None

    async def extract(
        self,
        text: str,
        schema: type[BaseModel],
        system_prompt: str,
        temperature: float = 0.0,
    ) -> tuple[BaseModel, ExtractionMeta]:
        start = time.monotonic()

        # Dynamic model resolution based on loaded models
        active_models = await _get_active_models()
        target_model = settings.LM_STUDIO_MODEL

        if target_model and target_model in active_models:
            self._model = target_model
        elif active_models:
            self._model = active_models[0]
            log.info(
                "lm_studio_fallback_to_active_model",
                fallback_model=self._model,
                target_model=target_model,
            )
        else:
            self._model = target_model or "qwen2.5-7b-instruct"
            log.info("lm_studio_no_active_models_found", default_model=self._model)

        # 1. Try standard JSON_SCHEMA mode natively via AsyncOpenAI
        try:
            log.info("lm_studio_attempting_json_schema", model=self._model)
            raw_response = await self._openai_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text},
                ],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": schema.__name__,
                        "strict": False,
                        "schema": schema.model_json_schema(),
                    },
                },
                temperature=temperature,
                timeout=300.0,
            )

            choice = raw_response.choices[0]
            content = choice.message.content or ""
            reasoning_content = getattr(choice.message, "reasoning_content", None) or ""

            # Fallback if reasoning_content was used instead of content (common in Qwen/reasoning models in LM Studio)
            if not content.strip() and reasoning_content.strip():
                log.info("lm_studio_reasoning_content_fallback", length=len(reasoning_content))
                content = reasoning_content

            # Parse the JSON
            raw_dict = json.loads(content)
            parsed = schema.model_validate(_normalize_invoice_json(raw_dict))

            latency_ms = (time.monotonic() - start) * 1000
            usage = raw_response.usage
            meta = ExtractionMeta(
                provider_name=self.provider_name,
                model_name=self._model,
                latency_ms=latency_ms,
                tokens_in=usage.prompt_tokens if usage else 0,
                tokens_out=usage.completion_tokens if usage else 0,
                cost_estimate=0.0,  # LM Studio is local
            )

            log.info(
                "llm_extraction",
                provider=self.provider_name,
                model=self._model,
                latency_ms=round(latency_ms),
                tokens_in=meta.tokens_in,
                tokens_out=meta.tokens_out,
            )
            return parsed, meta

        except Exception as exc:
            log.warning("lm_studio_json_schema_failed", error=str(exc))

            # 2. Fallback to MD_JSON (markdown-wrapped JSON parse)
            log.info("lm_studio_attempting_markdown_fallback", model=self._model)

            fallback_system_prompt = (
                f"{system_prompt}\n\n"
                f"You MUST return ONLY a valid JSON object matching this schema:\n"
                f"{json.dumps(schema.model_json_schema(), indent=2)}\n\n"
                f"Wrap your JSON in a markdown code block starting with ```json and ending with ```."
            )

            raw_response = await self._openai_client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": fallback_system_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=temperature,
            )

            choice = raw_response.choices[0]
            content = choice.message.content or ""
            reasoning_content = getattr(choice.message, "reasoning_content", None) or ""

            if not content.strip() and reasoning_content.strip():
                content = reasoning_content

            # Extract JSON from markdown code block
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_str = content

            try:
                raw_dict = json.loads(json_str)
                parsed = schema.model_validate(_normalize_invoice_json(raw_dict))
            except Exception as parse_exc:
                raise RuntimeError(
                    f"Both extraction attempts failed. "
                    f"Parse error: {parse_exc}. "
                    f"Response (first 300 chars): {content[:300]!r}"
                ) from parse_exc

            latency_ms = (time.monotonic() - start) * 1000
            usage = raw_response.usage
            meta = ExtractionMeta(
                provider_name=self.provider_name,
                model_name=self._model,
                latency_ms=latency_ms,
                tokens_in=usage.prompt_tokens if usage else 0,
                tokens_out=usage.completion_tokens if usage else 0,
                cost_estimate=0.0,
            )

            log.info(
                "llm_extraction_fallback",
                provider=self.provider_name,
                model=self._model,
                latency_ms=round(latency_ms),
                tokens_in=meta.tokens_in,
                tokens_out=meta.tokens_out,
            )
            return parsed, meta
