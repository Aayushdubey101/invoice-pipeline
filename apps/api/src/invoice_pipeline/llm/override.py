"""Per-request BYOK provider override — parsed from request headers, never persisted.

Browser sessions supply their own cloud provider API key on each upload request
instead of the server storing one. See CLAUDE.md Phase 13.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from fastapi import HTTPException, Request

CloudProviderName = Literal["openai", "anthropic", "gemini", "groq"]
_VALID_PROVIDERS: frozenset[str] = frozenset({"openai", "anthropic", "gemini", "groq"})


@dataclass(frozen=True)
class ProviderOverride:
    provider: CloudProviderName
    api_key: str
    model: str
    config: dict[str, Any] = field(default_factory=dict)


def parse_provider_override(request: Request, workspace: Any = None) -> ProviderOverride | None:
    """Read X-LLM-* headers into a ProviderOverride, or None if absent.

    Raises HTTPException(400) on a malformed/unknown override — fail loudly
    rather than silently falling back to the server's own provider.
    """
    provider = request.headers.get("X-LLM-Provider")
    if not provider:
        return None

    if provider not in _VALID_PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    api_key = request.headers.get("X-LLM-Api-Key", "")
    if not api_key and workspace and workspace.provider_preference:
        encrypted_key = workspace.provider_preference.get("encrypted_api_key")
        if encrypted_key:
            from invoice_pipeline.utils.encryption import decrypt
            try:
                api_key = decrypt(encrypted_key)
            except Exception:
                pass

    if not api_key:
        raise HTTPException(status_code=400, detail="X-LLM-Api-Key header is required")

    model = request.headers.get("X-LLM-Model", "")
    if not model:
        raise HTTPException(status_code=400, detail="X-LLM-Model header is required")

    config: dict[str, Any] = {}
    raw_config = request.headers.get("X-LLM-Config")
    if raw_config:
        try:
            config = json.loads(raw_config)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid X-LLM-Config JSON: {exc}")
        if not isinstance(config, dict):
            raise HTTPException(status_code=400, detail="X-LLM-Config must be a JSON object")

    return ProviderOverride(provider=provider, api_key=api_key, model=model, config=config)  # type: ignore[arg-type]
