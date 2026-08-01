"""Phase 13 BYOK — create_provider(override=...) bypasses cache/auto-detect."""

from unittest.mock import patch

import pytest

import invoice_pipeline.llm.factory as factory
from invoice_pipeline.llm.override import ProviderOverride


@pytest.mark.asyncio
async def test_override_builds_matching_provider_class() -> None:
    override = ProviderOverride(
        provider="openai", api_key="sk-test", model="gpt-4o-mini", config={}
    )
    with (
        patch("invoice_pipeline.llm.openai_client.instructor"),
        patch("invoice_pipeline.llm.openai_client.AsyncOpenAI"),
    ):
        provider = await factory.create_provider(override=override)

    assert provider.provider_name == "openai"
    assert provider._model == "gpt-4o-mini"


@pytest.mark.asyncio
async def test_override_does_not_touch_cached_singleton() -> None:
    factory._provider_instance = None
    override = ProviderOverride(
        provider="anthropic", api_key="sk-ant-test", model="claude-sonnet-4-5", config={}
    )
    with (
        patch("invoice_pipeline.llm.anthropic_client.instructor"),
        patch("invoice_pipeline.llm.anthropic_client.anthropic"),
    ):
        await factory.create_provider(override=override)

    assert factory._provider_instance is None


@pytest.mark.asyncio
async def test_override_config_passed_to_provider() -> None:
    override = ProviderOverride(
        provider="groq",
        api_key="gsk-test",
        model="llama-3.3-70b-versatile",
        config={"temperature": 0.7, "max_tokens": 512},
    )
    with (
        patch("invoice_pipeline.llm.groq_client.instructor"),
        patch("invoice_pipeline.llm.groq_client.AsyncOpenAI"),
    ):
        provider = await factory.create_provider(override=override)

    assert provider.provider_name == "groq"
    assert provider._config == {"temperature": 0.7, "max_tokens": 512}
