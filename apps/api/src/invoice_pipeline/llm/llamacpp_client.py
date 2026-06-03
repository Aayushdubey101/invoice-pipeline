"""llama.cpp provider (OpenAI-compatible local server).

Also compatible with LM Studio / Ollama OpenAI-compatible endpoints.
Local-only — no cost, dummy API key tolerated.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator
from typing import Any

import structlog
from httpx import AsyncClient
from openai import AsyncOpenAI
from pydantic import BaseModel

from invoice_pipeline.config import settings
from invoice_pipeline.llm.base import ExtractionMeta, NoLLMProviderConfigured

log = structlog.get_logger()

HEALTH_TIMEOUT_S = 2.0
REQUEST_TIMEOUT_S = 120.0


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _health_url(base_url: str) -> str:
    root = _normalize_base_url(base_url)
    if root.endswith("/v1"):
        root = root[: -len("/v1")]
    return f"{root}/health"


async def health_check(base_url: str | None = None) -> dict[str, Any]:
    target = base_url or settings.LLAMACPP_BASE_URL
    url = _health_url(target)
    started = time.monotonic()
    try:
        async with AsyncClient(timeout=HEALTH_TIMEOUT_S) as client:
            resp = await client.get(url)
            latency_ms = (time.monotonic() - started) * 1000
            ok = resp.status_code == 200
            body: dict[str, Any] | str
            try:
                body = resp.json()
            except Exception:
                body = resp.text[:200]
            return {
                "online": ok,
                "status_code": resp.status_code,
                "latency_ms": round(latency_ms, 2),
                "endpoint": url,
                "body": body,
            }
    except Exception as exc:
        return {
            "online": False,
            "error": str(exc),
            "endpoint": url,
            "message": "llama.cpp local server is not running",
        }


async def list_models(base_url: str | None = None) -> dict[str, Any]:
    target = _normalize_base_url(base_url or settings.LLAMACPP_BASE_URL)
    url = f"{target}/models"
    try:
        async with AsyncClient(timeout=HEALTH_TIMEOUT_S) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                return {"online": True, "models": [m["id"] for m in data]}
            return {"online": False, "models": [], "status_code": resp.status_code}
    except Exception as exc:
        return {
            "online": False,
            "models": [],
            "error": str(exc),
            "message": "llama.cpp local server is not running",
        }


class LlamaCppProvider:
    provider_name = "llamacpp"

    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
    ) -> None:
        resolved_url = (base_url or settings.LLAMACPP_BASE_URL).strip()
        if not resolved_url:
            raise NoLLMProviderConfigured("LLAMACPP_BASE_URL is empty.")
        self._base_url = _normalize_base_url(resolved_url)
        self._openai_client = AsyncOpenAI(
            base_url=self._base_url,
            api_key=api_key or settings.LLAMACPP_API_KEY or "not-needed",
        )
        self._model = model or settings.LLAMACPP_MODEL or "local-model"
        self._temperature = settings.LLAMACPP_TEMPERATURE
        self._max_tokens = settings.LLAMACPP_MAX_TOKENS

    async def extract(
        self,
        text: str,
        schema: type[BaseModel],
        system_prompt: str,
        temperature: float = 0.0,
    ) -> tuple[BaseModel, ExtractionMeta]:
        start = time.monotonic()
        effective_temp = temperature if temperature is not None else self._temperature

        log.info(
            "llamacpp_request",
            provider=self.provider_name,
            model=self._model,
            endpoint=self._base_url,
            temperature=effective_temp,
            max_tokens=self._max_tokens,
            input_chars=len(text),
        )

        try:
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
                temperature=effective_temp,
                max_tokens=self._max_tokens,
                timeout=REQUEST_TIMEOUT_S,
            )
            choice = raw_response.choices[0]
            content = choice.message.content or ""
            reasoning = getattr(choice.message, "reasoning_content", None) or ""
            if not content.strip() and reasoning.strip():
                content = reasoning
            parsed = schema.model_validate_json(content)
            return parsed, self._build_meta(raw_response, start, mode="json_schema")
        except Exception as exc:
            log.warning("llamacpp_json_schema_failed", error=str(exc))

        fallback_system_prompt = (
            f"{system_prompt}\n\n"
            "You MUST return ONLY a valid JSON object matching this schema:\n"
            f"{json.dumps(schema.model_json_schema(), indent=2)}\n\n"
            "Wrap the JSON in a markdown code block starting with ```json and ending with ```."
        )

        raw_response = await self._openai_client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": fallback_system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=effective_temp,
            max_tokens=self._max_tokens,
            timeout=REQUEST_TIMEOUT_S,
        )
        choice = raw_response.choices[0]
        content = choice.message.content or ""
        reasoning = getattr(choice.message, "reasoning_content", None) or ""
        if not content.strip() and reasoning.strip():
            content = reasoning

        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", content)
        json_str = match.group(1) if match else content
        parsed = schema.model_validate_json(json_str)
        return parsed, self._build_meta(raw_response, start, mode="markdown_fallback")

    async def stream(
        self,
        text: str,
        system_prompt: str,
        temperature: float | None = None,
    ) -> AsyncIterator[str]:
        effective_temp = temperature if temperature is not None else self._temperature
        stream = await self._openai_client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            temperature=effective_temp,
            max_tokens=self._max_tokens,
            stream=True,
            timeout=REQUEST_TIMEOUT_S,
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta

    def _build_meta(self, raw_response: Any, start: float, mode: str) -> ExtractionMeta:
        latency_ms = (time.monotonic() - start) * 1000
        usage = getattr(raw_response, "usage", None)
        tokens_in = getattr(usage, "prompt_tokens", 0) if usage else 0
        tokens_out = getattr(usage, "completion_tokens", 0) if usage else 0
        log.info(
            "llamacpp_response",
            provider=self.provider_name,
            model=self._model,
            mode=mode,
            latency_ms=round(latency_ms),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
        return ExtractionMeta(
            provider_name=self.provider_name,
            model_name=self._model,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_estimate=0.0,
        )
