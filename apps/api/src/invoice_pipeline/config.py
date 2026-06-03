import json
from enum import Enum
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMProviderName(str, Enum):
    AUTO = "auto"
    LM_STUDIO = "lm_studio"
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
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

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://invoice:invoice@localhost:5432/invoice_pipeline"
    DATABASE_URL_SYNC: str = "postgresql://invoice:invoice@localhost:5432/invoice_pipeline"

    # ChromaDB
    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8001
    CHROMA_VENDOR_COLLECTION: str = "vendors"

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

    # Pipeline
    LOW_CONFIDENCE_THRESHOLD: float = 0.75
    MAX_UPLOAD_SIZE_MB: int = 25
    SCANNED_PDF_CHARS_PER_PAGE_THRESHOLD: int = 50

    # Webhooks
    REVIEW_WEBHOOK_URL: str = ""

    @property
    def max_upload_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


# ── Runtime overrides (persisted across restarts) ────────────────────────────
RUNTIME_OVERRIDES_PATH = Path(__file__).resolve().parent.parent.parent / "runtime_settings.json"

_PERSISTABLE_FIELDS: tuple[str, ...] = (
    "LLM_PROVIDER",
    "LM_STUDIO_BASE_URL",
    "LM_STUDIO_MODEL",
    "OPENAI_API_KEY",
    "OPENAI_MODEL",
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_MODEL",
    "GEMINI_API_KEY",
    "GEMINI_MODEL",
    "LLAMACPP_BASE_URL",
    "LLAMACPP_MODEL",
    "LLAMACPP_API_KEY",
    "LLAMACPP_CONTEXT_LENGTH",
    "LLAMACPP_TEMPERATURE",
    "LLAMACPP_MAX_TOKENS",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
)


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
        if field in data:
            setattr(target, field, _coerce(field, data[field]))


def save_runtime_overrides(source: Settings) -> None:
    payload: dict[str, object] = {}
    for field in _PERSISTABLE_FIELDS:
        value = getattr(source, field)
        if isinstance(value, Enum):
            value = value.value
        payload[field] = value
    RUNTIME_OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    RUNTIME_OVERRIDES_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


settings = Settings()
load_runtime_overrides(settings)
