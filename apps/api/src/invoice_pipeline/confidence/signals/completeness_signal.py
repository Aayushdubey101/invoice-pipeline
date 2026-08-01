from __future__ import annotations

from invoice_pipeline.schemas import Document, FieldValue
from invoice_pipeline.confidence.signals.base import BaseSignal
from invoice_pipeline.confidence.models import ConfidenceSignal

class ExtractionCompletenessSignal(BaseSignal):
    name = "completeness"
    weight = 0.10
    description = "Ratio of non-null extracted fields."

    async def compute(self, doc: Document) -> ConfidenceSignal:
        if not doc.extracted:
            return ConfidenceSignal(name=self.name, score=0.0, weight=self.weight, description="No extraction found.")

        total = 0
        non_null = 0
        for field_name, fv in doc.extracted:
            if field_name == "line_items":
                continue
            if isinstance(fv, FieldValue):
                total += 1
                if fv.value is not None and fv.value.strip() != "":
                    non_null += 1

        score = (non_null / total) if total > 0 else 0.0

        return ConfidenceSignal(
            name=self.name,
            score=score,
            weight=self.weight,
            description=self.description,
        )
