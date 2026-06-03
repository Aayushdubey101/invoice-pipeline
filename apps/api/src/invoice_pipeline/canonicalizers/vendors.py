"""
Vendor matching:
  1. rapidfuzz score >= 90 on canonical_name + aliases → accept
  2. sentence-transformers + Chroma cosine >= 0.85 → accept
  3. Neither → new vendor row status='pending_review'
Returns (vendor_id, matched: bool)
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.config import settings
from invoice_pipeline.db.models import Vendor

log = structlog.get_logger()

_FUZZY_THRESHOLD = 90
_COSINE_THRESHOLD = 0.85


async def match_or_create_vendor(
    vendor_name: str,
    session: AsyncSession,
) -> tuple[str, bool]:
    """Return (vendor_id, vendor_matched_boolean)."""
    if not vendor_name.strip():
        return str(uuid.uuid4()), False

    vendors = (await session.execute(select(Vendor))).scalars().all()

    # 1. rapidfuzz
    vendor_id = _fuzzy_match(vendor_name, vendors)
    if vendor_id:
        log.info("vendor_matched", method="rapidfuzz", vendor_name=vendor_name, vendor_id=vendor_id)
        return vendor_id, True

    # 2. Embedding + Chroma
    vendor_id = await _embedding_match(vendor_name, vendors)
    if vendor_id:
        log.info("vendor_matched", method="embedding", vendor_name=vendor_name, vendor_id=vendor_id)
        return vendor_id, True

    # 3. Create pending
    new_vendor = Vendor(
        id=str(uuid.uuid4()),
        canonical_name=vendor_name,
        aliases=[],
        status="pending_review",
    )
    session.add(new_vendor)
    await session.flush()
    log.info("vendor_created", vendor_name=vendor_name, vendor_id=new_vendor.id)
    return new_vendor.id, False


def _fuzzy_match(name: str, vendors: Sequence[Vendor]) -> str | None:
    try:
        from rapidfuzz import fuzz, process

        candidates: dict[str, str] = {}  # display_name → vendor_id
        for v in vendors:
            candidates[v.canonical_name] = v.id
            for alias in v.aliases or []:
                candidates[str(alias)] = v.id

        if not candidates:
            return None

        result = process.extractOne(name, list(candidates.keys()), scorer=fuzz.token_sort_ratio)
        if result and result[1] >= _FUZZY_THRESHOLD:
            return candidates[result[0]]
        return None
    except Exception:
        return None


async def _embedding_match(name: str, vendors: Sequence[Vendor]) -> str | None:
    try:
        import chromadb
        from sentence_transformers import SentenceTransformer

        client = chromadb.HttpClient(host=settings.CHROMA_HOST, port=settings.CHROMA_PORT)
        collection = client.get_or_create_collection(settings.CHROMA_VENDOR_COLLECTION)

        model = SentenceTransformer("all-MiniLM-L6-v2")
        query_vec = model.encode(name).tolist()

        results = collection.query(query_embeddings=[query_vec], n_results=1)
        if not results["distances"] or not results["distances"][0]:
            return None

        # Chroma returns L2 distance; convert to cosine similarity approximation
        # For normalized vectors: cosine_sim = 1 - (L2^2 / 2)
        dist = results["distances"][0][0]
        cosine_sim = 1.0 - (dist**2) / 2.0

        if cosine_sim >= _COSINE_THRESHOLD:
            vendor_id = results["ids"][0][0]
            return vendor_id
        return None
    except Exception:
        return None
