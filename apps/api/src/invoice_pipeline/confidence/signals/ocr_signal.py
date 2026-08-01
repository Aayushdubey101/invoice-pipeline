from __future__ import annotations

from invoice_pipeline.schemas import Document
from invoice_pipeline.confidence.signals.base import BaseSignal
from invoice_pipeline.confidence.models import ConfidenceSignal

class OCRConfidenceSignal(BaseSignal):
    name = "ocr"
    weight = 0.15
    description = "OCR confidence based on word-level metrics or heuristics."

    async def compute(self, doc: Document) -> ConfidenceSignal:
        score = 0.8
        return ConfidenceSignal(
            name=self.name,
            score=score,
            weight=self.weight,
            description=self.description,
        )
