from __future__ import annotations

from invoice_pipeline.schemas import Document
from invoice_pipeline.confidence.signals.base import BaseSignal
from invoice_pipeline.confidence.models import ConfidenceSignal

class VendorMatchSignal(BaseSignal):
    name = "vendor"
    weight = 0.10
    description = "Confidence based on vendor matching."

    async def compute(self, doc: Document) -> ConfidenceSignal:
        score = 1.0 if doc.vendor_matched else 0.5
        return ConfidenceSignal(
            name=self.name,
            score=score,
            weight=self.weight,
            description=self.description,
        )
