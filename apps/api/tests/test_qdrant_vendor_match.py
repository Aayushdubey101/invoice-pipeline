from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from invoice_pipeline.canonicalizers.vendors import match_or_create_vendor
from invoice_pipeline.db.models import Base, Vendor

pytestmark = pytest.mark.asyncio

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


@patch("invoice_pipeline.canonicalizers.vendors._generate_embedding")
@patch("invoice_pipeline.canonicalizers.qdrant_client.get_qdrant_client")
async def test_qdrant_vendor_match(
    mock_get_client: MagicMock,
    mock_generate: MagicMock,
    db_session: AsyncSession,
) -> None:
    # Setup Qdrant mock
    mock_qdrant = AsyncMock()
    mock_get_client.return_value = mock_qdrant
    mock_generate.return_value = [0.1] * 384

    # Simulate Qdrant finding a match
    class MockScoredPoint:
        id = "matched-id-123"
        score = 0.95

    class MockQueryResponse:
        points = [MockScoredPoint()]

    mock_qdrant.query_points.return_value = MockQueryResponse()

    # Run match
    vendor_id, matched = await match_or_create_vendor("Matched Vendor", db_session, "ws_1")

    assert matched is True
    assert vendor_id == "matched-id-123"
    mock_qdrant.query_points.assert_called_once()


@patch("invoice_pipeline.canonicalizers.vendors._generate_embedding")
@patch("invoice_pipeline.canonicalizers.qdrant_client.get_qdrant_client")
async def test_qdrant_vendor_create_write_path(
    mock_get_client: MagicMock,
    mock_generate: MagicMock,
    db_session: AsyncSession,
) -> None:
    # Setup Qdrant mock
    mock_qdrant = AsyncMock()
    mock_get_client.return_value = mock_qdrant
    mock_generate.return_value = [0.1] * 384

    # Simulate Qdrant finding NO match
    class MockQueryResponse:
        points = []

    mock_qdrant.query_points.return_value = MockQueryResponse()

    # Run match
    vendor_id, matched = await match_or_create_vendor("New Vendor", db_session, "ws_1")

    assert matched is False

    # Check vendor was created in DB
    from sqlalchemy import select
    vendor = (await db_session.execute(select(Vendor).where(Vendor.id == vendor_id))).scalar_one()
    assert vendor.canonical_name == "New Vendor"
    assert vendor.status == "pending_review"
    assert vendor.embedding_id == vendor.id

    # Check that Qdrant upsert was called with the new embedding
    mock_qdrant.upsert.assert_called_once()
    kwargs = mock_qdrant.upsert.call_args.kwargs
    points = kwargs["points"]
    assert len(points) == 1
    assert points[0].id == vendor.id
    assert points[0].payload["canonical_name"] == "New Vendor"
    assert points[0].payload["workspace_id"] == "ws_1"
