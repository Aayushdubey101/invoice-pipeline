import structlog
from invoice_pipeline.config import settings

log = structlog.get_logger()

_client = None


def get_qdrant_client():
    """Return a singleton AsyncQdrantClient instance."""
    global _client
    if _client is None:
        from qdrant_client import AsyncQdrantClient

        if settings.QDRANT_URL:
            _client = AsyncQdrantClient(
                url=settings.QDRANT_URL,
                api_key=settings.QDRANT_API_KEY or None,
            )
        else:
            _client = AsyncQdrantClient(
                host=settings.QDRANT_HOST,
                port=settings.QDRANT_PORT,
            )
    return _client


async def ensure_qdrant_collection() -> None:
    """Ensure the vendors collection exists in Qdrant with correct settings."""
    try:
        from qdrant_client.http import models

        client = get_qdrant_client()
        
        # Check if collection exists
        try:
            await client.get_collection(settings.QDRANT_VENDOR_COLLECTION)
        except Exception as e:
            if "Not found: Collection" in str(e):
                await client.create_collection(
                    collection_name=settings.QDRANT_VENDOR_COLLECTION,
                    vectors_config=models.VectorParams(
                        size=384,  # all-MiniLM-L6-v2 dimension
                        distance=models.Distance.COSINE,
                    ),
                )
                log.info("qdrant_collection_created", collection=settings.QDRANT_VENDOR_COLLECTION)
            else:
                raise
    except Exception as e:
        log.warning("qdrant_setup_failed", error=str(e))
