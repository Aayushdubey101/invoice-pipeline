from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

from invoice_pipeline.schemas import CanonicalizedInvoice, Document, Invoice
from invoice_pipeline.confidence.models import ConfidenceSignal

@dataclass
class SignalContext:
    document: Document
    raw_text: str
    extracted: Invoice
    canonicalized: CanonicalizedInvoice | None
    validation_report: dict[str, Any] | None
    vendor_matched: bool

class BaseSignal(abc.ABC):
    name: str
    weight: float
    description: str

    @abc.abstractmethod
    async def compute(self, doc: Document) -> ConfidenceSignal:
        pass
