from typing import Protocol

from invoice_pipeline.schemas import Page


class OCREngine(Protocol):
    async def extract_pages(self, file_bytes: bytes, mime_type: str) -> list[Page]: ...
