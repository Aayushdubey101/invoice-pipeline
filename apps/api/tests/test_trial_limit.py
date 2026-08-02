"""Phase 15 — free-trial gating for the platform's own .env LLM key."""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from invoice_pipeline.api.main import app
from invoice_pipeline.db.models import Base, Workspace
from invoice_pipeline.db.session import get_session
from invoice_pipeline.llm.base import ExtractionMeta
from invoice_pipeline.schemas import FieldValue
from invoice_pipeline.schemas import Invoice as ExtractedInvoice
from invoice_pipeline.services.trial import TRIAL_LIMIT, consume_trial_use

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession):
    async def override_get_session():
        yield db_session

    app.dependency_overrides[get_session] = override_get_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def mock_llm():
    invoice = ExtractedInvoice(
        invoice_number=FieldValue(value="INV-1", confidence=0.95, evidence="INV-1"),
        invoice_date=FieldValue(value="2024-01-15", confidence=0.9, evidence="2024-01-15"),
        vendor_name=FieldValue(value="Acme", confidence=0.92, evidence="Acme"),
        total_amount=FieldValue(value="100.00", confidence=0.96, evidence="$100.00"),
        currency=FieldValue(value="USD", confidence=0.99, evidence="USD"),
    )
    meta = ExtractionMeta(
        provider_name="openai", model_name="gpt-4o-mini", latency_ms=1.0,
        tokens_in=10, tokens_out=10, cost_estimate=0.0,
    )
    mock_provider = AsyncMock()
    mock_provider.extract = AsyncMock(return_value=(invoice, meta))
    with patch("invoice_pipeline.llm.factory._provider_instance", mock_provider):
        with patch("invoice_pipeline.stages.field_extract.get_provider", return_value=mock_provider):
            with patch("invoice_pipeline.stages.field_extract.create_provider", return_value=mock_provider):
                yield mock_provider


async def _make_workspace(session: AsyncSession) -> Workspace:
    ws = Workspace(workspace_type="guest")
    session.add(ws)
    await session.commit()
    return ws


@pytest.mark.asyncio
async def test_consume_trial_use_decrements_and_blocks_at_zero(db_session: AsyncSession) -> None:
    ws = await _make_workspace(db_session)
    assert ws.trial_uses_remaining == TRIAL_LIMIT

    for _ in range(TRIAL_LIMIT):
        assert await consume_trial_use(ws.id, db_session) is True

    assert await consume_trial_use(ws.id, db_session) is False


@pytest.mark.asyncio
async def test_upload_blocked_after_trial_exhausted(
    client: AsyncClient, db_session: AsyncSession, mock_llm
) -> None:
    ws = await _make_workspace(db_session)
    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()

    for i in range(TRIAL_LIMIT):
        res = await client.post(
            "/documents/upload",
            files={"file": (f"invoice{i}.pdf", pdf_bytes + bytes([i]), "application/pdf")},
            headers={"X-Workspace-Id": ws.id},
        )
        assert res.status_code == 202, res.text

    blocked = await client.post(
        "/documents/upload",
        files={"file": ("invoice_over_limit.pdf", pdf_bytes + b"\xff", "application/pdf")},
        headers={"X-Workspace-Id": ws.id},
    )
    assert blocked.status_code == 402
    assert "trial" in blocked.json()["detail"].lower()


@pytest.mark.asyncio
async def test_byok_override_bypasses_trial_counter(
    client: AsyncClient, db_session: AsyncSession, mock_llm
) -> None:
    ws = await _make_workspace(db_session)
    pdf_bytes = (FIXTURES / "sample_invoice.pdf").read_bytes()

    for i in range(TRIAL_LIMIT + 2):
        res = await client.post(
            "/documents/upload",
            files={"file": (f"byok{i}.pdf", pdf_bytes + bytes([i]), "application/pdf")},
            headers={
                "X-Workspace-Id": ws.id,
                "X-LLM-Provider": "openai",
                "X-LLM-Api-Key": "sk-user-own-key",
                "X-LLM-Model": "gpt-4o-mini",
            },
        )
        assert res.status_code == 202, res.text

    await db_session.refresh(ws)
    assert ws.trial_uses_remaining == TRIAL_LIMIT
