from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

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


@pytest.mark.asyncio
async def test_llamacpp_provider_init() -> None:
    from invoice_pipeline.llm.llamacpp_client import LlamaCppProvider

    with patch("invoice_pipeline.llm.llamacpp_client.settings") as s:
        s.LLAMACPP_BASE_URL = "http://localhost:8080/v1"
        s.LLAMACPP_MODEL = "llama3"
        s.LLAMACPP_API_KEY = "test-key"
        s.LLAMACPP_TEMPERATURE = 0.2
        s.LLAMACPP_MAX_TOKENS = 1000

        provider = LlamaCppProvider()
        assert provider.provider_name == "llamacpp"
        assert provider._base_url == "http://localhost:8080/v1"
        assert provider._model == "llama3"


@pytest.mark.asyncio
async def test_llamacpp_provider_extract_json_schema() -> None:
    expected = _mock_invoice()
    mock_completion = MagicMock()
    mock_completion.usage.prompt_tokens = 120
    mock_completion.usage.completion_tokens = 60
    mock_choice = MagicMock()
    mock_choice.message.content = expected.model_dump_json()
    mock_choice.message.reasoning_content = None
    mock_completion.choices = [mock_choice]

    from invoice_pipeline.llm.llamacpp_client import LlamaCppProvider

    with patch("invoice_pipeline.llm.llamacpp_client.AsyncOpenAI") as mock_async_openai:
        mock_client = AsyncMock()
        mock_async_openai.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_completion)

        provider = LlamaCppProvider(base_url="http://localhost:8080/v1", model="test-model")
        result, meta = await provider.extract(
            text="Invoice text", schema=Invoice, system_prompt="Extract invoice", temperature=0.1
        )

    assert isinstance(result, Invoice)
    assert result.invoice_number.value == "INV-001"
    assert meta.provider_name == "llamacpp"
    assert meta.tokens_in == 120
    assert meta.tokens_out == 60


@pytest.mark.asyncio
async def test_llamacpp_provider_extract_markdown_fallback() -> None:
    expected = _mock_invoice()

    # First call fails
    mock_completion_fail = MagicMock()
    mock_completion_fail.choices = []  # will raise error or create exception in parser

    # Second call (fallback) succeeds
    mock_completion_ok = MagicMock()
    mock_completion_ok.usage.prompt_tokens = 150
    mock_completion_ok.usage.completion_tokens = 70
    mock_choice = MagicMock()
    mock_choice.message.content = f"```json\n{expected.model_dump_json()}\n```"
    mock_choice.message.reasoning_content = None
    mock_completion_ok.choices = [mock_choice]

    from invoice_pipeline.llm.llamacpp_client import LlamaCppProvider

    with patch("invoice_pipeline.llm.llamacpp_client.AsyncOpenAI") as mock_async_openai:
        mock_client = AsyncMock()
        mock_async_openai.return_value = mock_client
        # Side effect: first raises exception, second returns fallback completion
        mock_client.chat.completions.create = AsyncMock(
            side_effect=[Exception("JSON schema mode unsupported"), mock_completion_ok]
        )

        provider = LlamaCppProvider(base_url="http://localhost:8080/v1", model="test-model")
        result, meta = await provider.extract(
            text="Invoice text", schema=Invoice, system_prompt="Extract invoice", temperature=0.1
        )

    assert isinstance(result, Invoice)
    assert result.invoice_number.value == "INV-001"
    assert meta.provider_name == "llamacpp"
    assert meta.tokens_in == 150
    assert meta.tokens_out == 70


@pytest.mark.asyncio
async def test_llamacpp_provider_stream() -> None:
    # Mock chunks
    mock_chunk_1 = MagicMock()
    mock_chunk_1.choices = [MagicMock()]
    mock_chunk_1.choices[0].delta.content = "Hello "
    mock_chunk_2 = MagicMock()
    mock_chunk_2.choices = [MagicMock()]
    mock_chunk_2.choices[0].delta.content = "world!"

    async def mock_async_generator():
        yield mock_chunk_1
        yield mock_chunk_2

    from invoice_pipeline.llm.llamacpp_client import LlamaCppProvider

    with patch("invoice_pipeline.llm.llamacpp_client.AsyncOpenAI") as mock_async_openai:
        mock_client = AsyncMock()
        mock_async_openai.return_value = mock_client
        mock_client.chat.completions.create = AsyncMock(return_value=mock_async_generator())

        provider = LlamaCppProvider(base_url="http://localhost:8080/v1", model="test-model")

        chunks = []
        async for chunk in provider.stream(text="Stream text", system_prompt="Stream system"):
            chunks.append(chunk)

    assert chunks == ["Hello ", "world!"]


@pytest.mark.asyncio
async def test_ollama_provider_init() -> None:
    from invoice_pipeline.llm.ollama_client import OllamaProvider

    with patch("invoice_pipeline.llm.ollama_client.settings") as s:
        s.OLLAMA_BASE_URL = "http://localhost:11434/v1"
        s.OLLAMA_MODEL = "gemma3"

        provider = OllamaProvider()
        assert provider.provider_name == "ollama"
        assert provider._base_url == "http://localhost:11434/v1"
        assert provider._model == "gemma3"
