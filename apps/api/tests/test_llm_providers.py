"""LLM provider tests — all providers mocked at the HTTP layer."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from invoice_pipeline.llm.base import ExtractionMeta, NoLLMProviderConfigured
from invoice_pipeline.schemas import FieldValue, Invoice


class SimpleSchema(BaseModel):
    name: str
    value: str


def _mock_invoice() -> Invoice:
    return Invoice(
        invoice_number=FieldValue(value="INV-001", confidence=0.95, evidence="INV-001"),
        invoice_date=FieldValue(value="2024-01-15", confidence=0.9, evidence="January 15, 2024"),
        total_amount=FieldValue(value="1234.56", confidence=0.98, evidence="$1,234.56"),
    )


# ── Factory auto-detect tests ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_factory_explicit_provider_openai() -> None:
    with patch("invoice_pipeline.llm.factory.settings") as mock_settings:
        mock_settings.LLM_PROVIDER.value = "openai"
        mock_settings.LLM_PROVIDER = MagicMock()
        mock_settings.LLM_PROVIDER.__eq__ = lambda self, other: str(other) == "openai"

        from invoice_pipeline.config import LLMProviderName

        with patch("invoice_pipeline.llm.factory.settings") as s:
            s.LLM_PROVIDER = LLMProviderName.OPENAI
            s.OPENAI_API_KEY = "sk-test"
            s.OPENAI_MODEL = "gpt-4o-mini"
            s.LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
            s.LM_STUDIO_MODEL = "test"
            s.ANTHROPIC_API_KEY = ""
            s.GEMINI_API_KEY = ""

            with patch("invoice_pipeline.llm.openai_client.instructor"):
                with patch("invoice_pipeline.llm.openai_client.AsyncOpenAI"):
                    from invoice_pipeline.llm.factory import create_provider

                    provider = await create_provider()
                    assert provider.provider_name == "openai"


@pytest.mark.asyncio
async def test_factory_auto_detects_lm_studio() -> None:
    from invoice_pipeline.config import LLMProviderName

    with patch("invoice_pipeline.llm.factory.settings") as s:
        s.LLM_PROVIDER = LLMProviderName.AUTO
        s.LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
        s.LM_STUDIO_MODEL = "test-model"
        s.OPENAI_API_KEY = ""
        s.ANTHROPIC_API_KEY = ""
        s.GEMINI_API_KEY = ""

        with patch("invoice_pipeline.llm.factory._lm_studio_reachable", return_value=True):
            with patch("invoice_pipeline.llm.lm_studio.AsyncOpenAI"):
                from invoice_pipeline.llm.factory import create_provider

                provider = await create_provider()
                assert provider.provider_name == "lm_studio"


@pytest.mark.asyncio
async def test_factory_auto_falls_back_to_anthropic() -> None:
    from invoice_pipeline.config import LLMProviderName

    with patch("invoice_pipeline.llm.factory.settings") as s:
        s.LLM_PROVIDER = LLMProviderName.AUTO
        s.LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
        s.ANTHROPIC_API_KEY = "sk-ant-test"
        s.ANTHROPIC_MODEL = "claude-sonnet-4-5"
        s.OPENAI_API_KEY = ""
        s.GEMINI_API_KEY = ""

        with patch("invoice_pipeline.llm.factory._lm_studio_reachable", return_value=False):
            with patch("invoice_pipeline.llm.anthropic_client.instructor"):
                with patch("invoice_pipeline.llm.anthropic_client.anthropic"):
                    from invoice_pipeline.llm.factory import create_provider

                    provider = await create_provider()
                    assert provider.provider_name == "anthropic"


@pytest.mark.asyncio
async def test_factory_raises_when_nothing_configured() -> None:
    from invoice_pipeline.config import LLMProviderName

    with patch("invoice_pipeline.llm.factory.settings") as s:
        s.LLM_PROVIDER = LLMProviderName.AUTO
        s.LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
        s.ANTHROPIC_API_KEY = ""
        s.OPENAI_API_KEY = ""
        s.GEMINI_API_KEY = ""

        with patch("invoice_pipeline.llm.factory._lm_studio_reachable", return_value=False):
            from invoice_pipeline.llm.factory import create_provider

            with pytest.raises(NoLLMProviderConfigured):
                await create_provider()


# ── Schema enforcement: LLM must return Invoice shape ─────────────────────────


@pytest.mark.asyncio
async def test_lm_studio_returns_invoice_schema() -> None:
    expected = _mock_invoice()
    mock_completion = MagicMock()
    mock_completion.usage.prompt_tokens = 100
    mock_completion.usage.completion_tokens = 50
    mock_choice = MagicMock()
    mock_choice.message.content = expected.model_dump_json()
    mock_choice.message.reasoning_content = None
    mock_completion.choices = [mock_choice]

    with patch("invoice_pipeline.llm.lm_studio.AsyncOpenAI") as mock_async_openai:
        mock_client = AsyncMock()
        mock_async_openai.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        from invoice_pipeline.llm.lm_studio import LMStudioProvider

        with patch("invoice_pipeline.llm.lm_studio.settings") as s:
            s.LM_STUDIO_BASE_URL = "http://localhost:1234/v1"
            s.LM_STUDIO_MODEL = "test"
            s.LLM_MAX_RETRIES = 1

            with patch("invoice_pipeline.llm.lm_studio._get_active_models", return_value=["test"]):
                provider = LMStudioProvider()
                result, meta = await provider.extract(
                    text="Invoice text",
                    schema=Invoice,
                    system_prompt="Extract invoice",
                    temperature=0.0,
                )

    assert isinstance(result, Invoice)
    assert result.invoice_number.value == "INV-001"
    assert isinstance(meta, ExtractionMeta)
    assert meta.provider_name == "lm_studio"
    assert meta.cost_estimate == 0.0


@pytest.mark.asyncio
async def test_openai_provider_schema_enforcement() -> None:
    expected = _mock_invoice()
    mock_completion = MagicMock()
    mock_completion.usage.prompt_tokens = 200
    mock_completion.usage.completion_tokens = 80

    with patch("invoice_pipeline.llm.openai_client.instructor") as mock_instructor:
        with patch("invoice_pipeline.llm.openai_client.AsyncOpenAI"):
            mock_client = AsyncMock()
            mock_instructor.from_openai.return_value = mock_client
            mock_client.chat.completions.create_with_completion = AsyncMock(
                return_value=(expected, mock_completion)
            )

            from invoice_pipeline.llm.openai_client import OpenAIProvider

            with patch("invoice_pipeline.llm.openai_client.settings") as s:
                s.OPENAI_API_KEY = "sk-test"
                s.OPENAI_MODEL = "gpt-4o-mini"
                s.LLM_MAX_RETRIES = 1

                provider = OpenAIProvider()
                result, meta = await provider.extract(
                    text="Invoice text",
                    schema=Invoice,
                    system_prompt="Extract invoice",
                    temperature=0.0,
                )

    assert isinstance(result, Invoice)
    assert meta.provider_name == "openai"
    assert meta.tokens_in == 200
    assert meta.cost_estimate > 0.0


@pytest.mark.asyncio
async def test_anthropic_provider_schema_enforcement() -> None:
    expected = _mock_invoice()
    mock_completion = MagicMock()
    mock_completion.usage.input_tokens = 150
    mock_completion.usage.output_tokens = 60

    with patch("invoice_pipeline.llm.anthropic_client.instructor") as mock_instructor:
        with patch("invoice_pipeline.llm.anthropic_client.anthropic"):
            mock_client = AsyncMock()
            mock_instructor.from_anthropic.return_value = mock_client
            mock_client.messages.create_with_completion = AsyncMock(
                return_value=(expected, mock_completion)
            )

            from invoice_pipeline.llm.anthropic_client import AnthropicProvider

            with patch("invoice_pipeline.llm.anthropic_client.settings") as s:
                s.ANTHROPIC_API_KEY = "sk-ant-test"
                s.ANTHROPIC_MODEL = "claude-sonnet-4-5"
                s.LLM_MAX_RETRIES = 1

                provider = AnthropicProvider()
                result, meta = await provider.extract(
                    text="Invoice text",
                    schema=Invoice,
                    system_prompt="Extract invoice",
                    temperature=0.0,
                )

    assert isinstance(result, Invoice)
    assert meta.provider_name == "anthropic"
    assert meta.tokens_in == 150


@pytest.mark.asyncio
async def test_gemini_provider_schema_enforcement() -> None:
    expected = _mock_invoice()
    mock_completion = MagicMock()
    mock_completion.usage_metadata.prompt_token_count = 120
    mock_completion.usage_metadata.candidates_token_count = 45

    with patch("invoice_pipeline.llm.gemini_client.instructor") as mock_instructor:
        with patch("invoice_pipeline.llm.gemini_client.genai"):
            mock_client = AsyncMock()
            mock_instructor.from_genai.return_value = mock_client
            mock_client.chat.completions.create_with_completion = AsyncMock(
                return_value=(expected, mock_completion)
            )

            from invoice_pipeline.llm.gemini_client import GeminiProvider

            with patch("invoice_pipeline.llm.gemini_client.settings") as s:
                s.GEMINI_API_KEY = "AIza-test"
                s.GEMINI_MODEL = "gemini-2.0-flash"
                s.LLM_MAX_RETRIES = 1

                provider = GeminiProvider()
                result, meta = await provider.extract(
                    text="Invoice text",
                    schema=Invoice,
                    system_prompt="Extract invoice",
                    temperature=0.0,
                )

    assert isinstance(result, Invoice)
    assert meta.provider_name == "gemini"
