import json
from enum import Enum
from pathlib import Path

from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderName(str, Enum):
    AUTO = "auto"
    LM_STUDIO = "lm_studio"
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    GROQ = "groq"
    LLAMACPP = "llamacpp"


class OCREngineName(str, Enum):
    PADDLEOCR = "paddleocr"
    TESSERACT = "tesseract"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_ignore_empty=True, extra="ignore")

    # App
    APP_NAME: str = "Invoice Intelligence Pipeline"
    APP_ENV: str = "development"
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Any) -> list[str]:
        if isinstance(v, str):
            v = v.strip()
            if (v.startswith("'") and v.endswith("'")) or (v.startswith('"') and v.endswith('"')):
                v = v[1:-1].strip()
            if v.startswith("[") and v.endswith("]"):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return [str(item).strip() for item in parsed if item]
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        elif isinstance(v, (list, tuple)):
            return [str(item).strip() for item in v if item]
        return ["http://localhost:3000"]

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://invoice:invoice@localhost:5432/invoice_pipeline"
    DATABASE_URL_SYNC: str = "postgresql://invoice:invoice@localhost:5432/invoice_pipeline"

    # Qdrant
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_URL: str = ""
    QDRANT_API_KEY: str = ""
    QDRANT_VENDOR_COLLECTION: str = "vendors"

    # LLM
    LLM_PROVIDER: LLMProviderName = LLMProviderName.AUTO
    LLM_TEMPERATURE: float = 0.0
    LLM_MAX_RETRIES: int = 2

    LM_STUDIO_BASE_URL: str = "http://localhost:1234/v1"
    LM_STUDIO_MODEL: str = "qwen2.5-7b-instruct"

    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    ANTHROPIC_API_KEY: str = ""
    ANTHROPIC_MODEL: str = "claude-sonnet-4-5"

    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-2.0-flash"

    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"
    GROQ_BASE_URL: str = "https://api.groq.com/openai/v1"
    GROQ_TEMPERATURE: float = 0.0
    GROQ_MAX_TOKENS: int = 4096
    GROQ_TIMEOUT: float = 60.0

    # Ollama (local, OpenAI-compatible)
    OLLAMA_BASE_URL: str = "http://localhost:11434/v1"
    OLLAMA_MODEL: str = "gemma3:4b"

    # llama.cpp (OpenAI-compatible local server)
    LLAMACPP_BASE_URL: str = "http://localhost:8080/v1"
    LLAMACPP_MODEL: str = "local-model"
    LLAMACPP_API_KEY: str = "not-needed"
    LLAMACPP_CONTEXT_LENGTH: int = 4096
    LLAMACPP_TEMPERATURE: float = 0.2
    LLAMACPP_MAX_TOKENS: int = 2048

    # OCR
    OCR_ENGINE: OCREngineName = OCREngineName.TESSERACT
    OCR_LANG: str = "eng+fra"  # tesseract langs; falls back to "eng" if a pack is missing

    # Pipeline
    LOW_CONFIDENCE_THRESHOLD: float = 0.75
    MAX_UPLOAD_SIZE_MB: int = 25
    SCANNED_PDF_CHARS_PER_PAGE_THRESHOLD: int = 50

    # Webhooks
    REVIEW_WEBHOOK_URL: str = ""

    # Optional email connector (Phase 11) — disabled by default, no effect when off
    EMAIL_IMPORT_ENABLED: bool = False
    EMAIL_CONNECT_TIMEOUT_SECONDS: int = 15

    # Clerk (Phase 14.8) — bearer-token verification for authenticated workspaces
    CLERK_JWKS_URL: str = ""
    CLERK_ISSUER: str = ""
    CLERK_AUDIENCE: str = ""

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


# ── Runtime overrides (persisted across restarts) ────────────────────────────
RUNTIME_OVERRIDES_PATH = (
    Path(__file__).resolve().parent.parent.parent / "config" / "runtime_settings.json"
)

_PERSISTABLE_FIELDS: tuple[str, ...] = (
    "LLM_PROVIDER",
    "LM_STUDIO_BASE_URL",
    "LM_STUDIO_MODEL",
    "LLAMACPP_BASE_URL",
    "LLAMACPP_MODEL",
    "LLAMACPP_API_KEY",
    "LLAMACPP_CONTEXT_LENGTH",
    "LLAMACPP_TEMPERATURE",
    "LLAMACPP_MAX_TOKENS",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
)


# Priority: runtime settings > .env > defaults. An empty runtime override for a
# secret must fall back to .env rather than permanently blanking it out.
# Phase 13: cloud provider keys (OPENAI/ANTHROPIC/GEMINI/GROQ) are no longer
# runtime-PATCH-able or persisted to disk — they're browser-session-only (BYOK,
# see llm/override.py). LLAMACPP_API_KEY stays: it's a local provider, no real
# secret (dummy key tolerated).
_API_KEY_FIELDS = frozenset({"LLAMACPP_API_KEY"})


def _coerce(field: str, value: object) -> object:
    if field == "LLM_PROVIDER" and isinstance(value, str):
        return LLMProviderName(value)
    return value


def load_runtime_overrides(target: Settings) -> None:
    if not RUNTIME_OVERRIDES_PATH.exists():
        return
    try:
        data = json.loads(RUNTIME_OVERRIDES_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for field in _PERSISTABLE_FIELDS:
        if field not in data:
            continue
        value = data[field]
        if field in _API_KEY_FIELDS and not value:
            continue  # empty override -> keep the .env-loaded value
        setattr(target, field, _coerce(field, value))


def save_runtime_overrides(source: Settings) -> None:
    payload: dict[str, object] = {}
    for field in _PERSISTABLE_FIELDS:
        value = getattr(source, field)
        if isinstance(value, Enum):
            value = value.value
        payload[field] = value
    RUNTIME_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_OVERRIDES_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def reset_runtime_overrides(target: Settings) -> None:
    """Drop the persisted local-provider overrides and restore `.env` defaults.

    Local-provider settings (Ollama/LM Studio/llama.cpp) are a single
    instance-wide file, unlike cloud provider keys which are already
    browser-session-only (see llm/override.py). A guest changing them would
    otherwise permanently affect every other user of this deployment, so a
    guest workspace ending must reset them back to `.env`.
    """
    RUNTIME_OVERRIDES_PATH.unlink(missing_ok=True)
    fresh = Settings()
    for field in _PERSISTABLE_FIELDS:
        setattr(target, field, getattr(fresh, field))


settings = Settings()
load_runtime_overrides(settings)
