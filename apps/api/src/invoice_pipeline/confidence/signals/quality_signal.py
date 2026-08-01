from __future__ import annotations

from invoice_pipeline.schemas import Document
from invoice_pipeline.confidence.signals.base import BaseSignal
from invoice_pipeline.confidence.models import ConfidenceSignal

class DocumentQualitySignal(BaseSignal):
    name = "quality"
    weight = 0.05
    description = "Document quality heuristic based on text length."

    async def compute(self, doc: Document) -> ConfidenceSignal:
        text_len = len(doc.raw_text)
        if text_len < 50:
            score = 0.2
        elif text_len < 200:
            score = 0.5
        elif text_len > 20000:
            score = 0.4
        elif text_len > 10000:
            score = 0.6
        else:
            score = 0.9

        return ConfidenceSignal(
            name=self.name,
            score=score,
            weight=self.weight,
            description=self.description,
        )
