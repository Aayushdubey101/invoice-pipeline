"""
Seed vendor master list into DB + ChromaDB.
  uv run python scripts/seed_vendors.py
"""

import asyncio
import uuid

import structlog

log = structlog.get_logger()

_SEED_VENDORS = [
    {
        "canonical_name": "Acme Corp",
        "aliases": ["ACME Corporation", "Acme Inc", "ACME CORP"],
        "address": "123 Main St, Springfield, USA",
        "tax_id": "12-3456789",
    },
    {
        "canonical_name": "Beta Inc",
        "aliases": ["Beta Incorporated", "BETA INC"],
        "address": "456 Oak Ave, Portland, USA",
        "tax_id": "98-7654321",
    },
    {
        "canonical_name": "Gamma Services LLC",
        "aliases": ["Gamma Services", "Gamma LLC"],
        "address": "789 Pine Rd, Austin, USA",
        "tax_id": "55-1234567",
    },
    {
        "canonical_name": "Delta Solutions",
        "aliases": ["Delta Solutions Inc", "Delta"],
        "address": "321 Elm Blvd, Seattle, USA",
    },
    {
        "canonical_name": "Epsilon Tech",
        "aliases": ["Epsilon Technology", "EpsilonTech"],
        "address": "654 Maple Dr, Boston, USA",
    },
]


async def seed() -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from invoice_pipeline.config import settings
    from invoice_pipeline.db.models import Vendor

    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        for v in _SEED_VENDORS:
            existing = (
                await session.execute(
                    select(Vendor).where(Vendor.canonical_name == v["canonical_name"])
                )
            ).scalar_one_or_none()

            if existing:
                log.info("vendor_exists", name=v["canonical_name"])
                continue

            vendor = Vendor(
                id=str(uuid.uuid4()),
                canonical_name=v["canonical_name"],
                aliases=v.get("aliases", []),
                address=v.get("address"),
                tax_id=v.get("tax_id"),
                status="active",
            )
            session.add(vendor)
            log.info("vendor_seeded", name=v["canonical_name"])

        await session.commit()

    await engine.dispose()

    # Seed Qdrant embeddings (optional — skips if ml group not installed)
    await _seed_qdrant()


async def _seed_qdrant() -> None:
    try:
        from qdrant_client.http import models
        from sentence_transformers import SentenceTransformer

        from invoice_pipeline.canonicalizers.qdrant_client import ensure_qdrant_collection, get_qdrant_client
        from invoice_pipeline.config import settings
        from invoice_pipeline.db.models import LEGACY_WORKSPACE_ID

        await ensure_qdrant_collection()
        client = get_qdrant_client()
        model = SentenceTransformer("all-MiniLM-L6-v2")

        for v in _SEED_VENDORS:
            name = v["canonical_name"]
            vendor_id = str(uuid.uuid4())  # placeholder; real seed would use DB id
            embedding = model.encode(name).tolist()
            
            await client.upsert(
                collection_name=settings.QDRANT_VENDOR_COLLECTION,
                points=[
                    models.PointStruct(
                        id=vendor_id,
                        vector=embedding,
                        payload={
                            "canonical_name": name,
                            "workspace_id": LEGACY_WORKSPACE_ID,
                        },
                    )
                ],
            )
            log.info("vendor_qdrant_seeded", name=name)

        log.info("qdrant_seed_complete", count=len(_SEED_VENDORS))
    except ImportError:
        log.info("qdrant_seed_skipped", reason="ml group not installed")
    except Exception as exc:
        log.warning("qdrant_seed_failed", error=str(exc))


if __name__ == "__main__":
    asyncio.run(seed())
