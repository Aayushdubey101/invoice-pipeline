from __future__ import annotations

from invoice_pipeline.schemas import Document, FieldValue
from invoice_pipeline.confidence.signals.base import BaseSignal
from invoice_pipeline.confidence.models import ConfidenceSignal

class LLMConfidenceSignal(BaseSignal):
    name = "llm"
    weight = 0.25
    description = "LLM self-reported confidence across extracted fields."

    async def compute(self, doc: Document) -> ConfidenceSignal:
        if not doc.extracted:
            return ConfidenceSignal(name=self.name, score=0.0, weight=self.weight, description="No extraction found.")
        
        confidences = []
        for field_name, fv in doc.extracted:
            if isinstance(fv, FieldValue):
                confidences.append(fv.confidence)
        
        for li in doc.extracted.line_items:
            for field_name, fv in li:
                if isinstance(fv, FieldValue):
                    confidences.append(fv.confidence)
                    
        score = sum(confidences) / len(confidences) if confidences else 0.0
        return ConfidenceSignal(
            name=self.name,
            score=score,
            weight=self.weight,
            description=self.description,
        )
