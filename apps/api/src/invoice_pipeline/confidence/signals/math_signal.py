from __future__ import annotations

from decimal import Decimal

from invoice_pipeline.schemas import Document
from invoice_pipeline.canonicalizers.currency import parse_amount
from invoice_pipeline.confidence.signals.base import BaseSignal
from invoice_pipeline.confidence.models import ConfidenceSignal

class MathConsistencySignal(BaseSignal):
    name = "math"
    weight = 0.15
    description = "Math consistency check for subtotal, tax, and total."

    async def compute(self, doc: Document) -> ConfidenceSignal:
        if not doc.extracted:
            return ConfidenceSignal(name=self.name, score=0.5, weight=self.weight, description="No extraction found.")

        subtotal = parse_amount(doc.extracted.subtotal.value)
        tax = parse_amount(doc.extracted.tax_amount.value)
        total = parse_amount(doc.extracted.total_amount.value)

        if subtotal is None or tax is None or total is None:
            return ConfidenceSignal(name=self.name, score=0.5, weight=self.weight, description="Missing amounts.")

        calc_total = subtotal + tax
        diff = abs(calc_total - total)

        if diff == 0:
            score = 1.0
        else:
            tolerance = abs(total) * Decimal("0.01")
            if diff <= tolerance:
                score = 0.8
            else:
                score = 0.3

        return ConfidenceSignal(
            name=self.name,
            score=score,
            weight=self.weight,
            description=self.description,
        )
