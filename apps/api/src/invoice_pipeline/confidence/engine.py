from __future__ import annotations

import structlog

from invoice_pipeline.schemas import Document
from invoice_pipeline.confidence.models import ConfidenceBreakdown, ConfidenceSignal
from invoice_pipeline.confidence.signals.base import BaseSignal
from invoice_pipeline.confidence.signals import ALL_SIGNALS

log = structlog.get_logger()

class ConfidenceEngine:
    def __init__(self, signals: list[BaseSignal] | None = None) -> None:
        self.signals = signals if signals is not None else list(ALL_SIGNALS)

    async def compute(self, doc: Document) -> ConfidenceBreakdown:
        breakdown_signals = []
        
        for signal in self.signals:
            try:
                sig_result = await signal.compute(doc)
                breakdown_signals.append(sig_result)
            except Exception as exc:
                log.error(
                    "confidence_signal_error",
                    signal=signal.name,
                    error=str(exc),
                    document_id=doc.document_id,
                )
                breakdown_signals.append(
                    ConfidenceSignal(
                        name=signal.name,
                        score=0.5,
                        weight=signal.weight,
                        description=f"Error computing signal: {exc}",
                    )
                )

        return ConfidenceBreakdown(signals=breakdown_signals)
