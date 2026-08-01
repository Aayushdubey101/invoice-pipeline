"""
Vendor matching:
  1. rapidfuzz score >= 90 on canonical_name + aliases → accept
  2. sentence-transformers + Chroma cosine >= 0.85 → accept
  3. Neither → new vendor row status='pending_review'
Returns (vendor_id, matched: bool)
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.config import settings
from invoice_pipeline.db.models import LEGACY_WORKSPACE_ID, Vendor

if TYPE_CHECKING:
    from sentence_transformers import SentenceTransformer

log = structlog.get_logger()

_FUZZY_THRESHOLD = 90
_COSINE_THRESHOLD = 0.85

# Loaded once per process and reused — re-constructing SentenceTransformer on
# every call re-reads/re-downloads the model each time.
_model: "SentenceTransformer | None" = None


def _get_model() -> "SentenceTransformer":
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


async def match_or_create_vendor(
    vendor_name: str,
    session: AsyncSession,
    workspace_id: str = LEGACY_WORKSPACE_ID,
) -> tuple[str, bool]:
    """Return (vendor_id, vendor_matched_boolean)."""
    if not vendor_name.strip():
        return str(uuid.uuid4()), False

    vendors = (
        (await session.execute(select(Vendor).where(Vendor.workspace_id == workspace_id)))
        .scalars()
        .all()
    )

    # 1. rapidfuzz
    vendor_id = _fuzzy_match(vendor_name, vendors)
    if vendor_id:
        log.info("vendor_matched", method="rapidfuzz", vendor_name=vendor_name, vendor_id=vendor_id)
        return vendor_id, True

    # 2. Embedding + Qdrant
    vendor_id = await _embedding_match(vendor_name, workspace_id)
    if vendor_id:
        log.info("vendor_matched", method="embedding", vendor_name=vendor_name, vendor_id=vendor_id)
        return vendor_id, True

    # 3. Create pending
    new_vendor = Vendor(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        canonical_name=vendor_name,
        aliases=[],
        status="pending_review",
    )

    # 4. Write path: store embedding in Qdrant
    try:
        from qdrant_client.http import models

        from invoice_pipeline.canonicalizers.qdrant_client import get_qdrant_client

        vec = await asyncio.to_thread(_generate_embedding, vendor_name)
        client = get_qdrant_client()
        await client.upsert(
            collection_name=settings.QDRANT_VENDOR_COLLECTION,
            points=[
                models.PointStruct(
                    id=new_vendor.id,
                    vector=vec,
                    payload={
                        "canonical_name": vendor_name,
                        "workspace_id": workspace_id,
                    },
                )
            ],
        )
        new_vendor.embedding_id = new_vendor.id
    except Exception as exc:
        log.debug("vendor_embedding_write_skipped", error=str(exc))

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


def _generate_embedding(name: str) -> list[float]:
    return _get_model().encode(name).tolist()


async def _embedding_match(name: str, workspace_id: str) -> str | None:
    try:
        from qdrant_client.http import models

        from invoice_pipeline.canonicalizers.qdrant_client import get_qdrant_client

        query_vec = await asyncio.to_thread(_generate_embedding, name)
        client = get_qdrant_client()

        response = await client.query_points(
            collection_name=settings.QDRANT_VENDOR_COLLECTION,
            query=query_vec,
            query_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="workspace_id", match=models.MatchValue(value=workspace_id)
                    )
                ]
            ),
            limit=1,
            score_threshold=_COSINE_THRESHOLD,
        )
        if response.points:
            return str(response.points[0].id)
        return None
    except Exception as exc:
        log.debug("embedding_match_skipped", error=str(exc))
        return None
