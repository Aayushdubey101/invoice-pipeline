from __future__ import annotations

from invoice_pipeline.schemas import Document
from invoice_pipeline.confidence.signals.base import BaseSignal
from invoice_pipeline.confidence.models import ConfidenceSignal

class ValidationScoreSignal(BaseSignal):
    name = "validation"
    weight = 0.20
    description = "Confidence based on phase 1 validation report."

    async def compute(self, doc: Document) -> ConfidenceSignal:
        score = 0.5
        if doc.validation_report:
            passed = doc.validation_report.get("passed", 0)
            failed = doc.validation_report.get("failed", 0)
            warnings = doc.validation_report.get("warnings", 0)
            total = passed + failed + warnings
            if total > 0:
                score = passed / total
        
        return ConfidenceSignal(
            name=self.name,
            score=score,
            weight=self.weight,
            description=self.description,
        )
