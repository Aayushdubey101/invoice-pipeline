from __future__ import annotations

from invoice_pipeline.confidence.signals.base import BaseSignal
from invoice_pipeline.confidence.signals.ocr_signal import OCRConfidenceSignal
from invoice_pipeline.confidence.signals.llm_signal import LLMConfidenceSignal
from invoice_pipeline.confidence.signals.validation_signal import ValidationScoreSignal
from invoice_pipeline.confidence.signals.vendor_signal import VendorMatchSignal
from invoice_pipeline.confidence.signals.math_signal import MathConsistencySignal
from invoice_pipeline.confidence.signals.completeness_signal import ExtractionCompletenessSignal
from invoice_pipeline.confidence.signals.quality_signal import DocumentQualitySignal

ALL_SIGNALS: list[BaseSignal] = [
    OCRConfidenceSignal(),
    LLMConfidenceSignal(),
    ValidationScoreSignal(),
    VendorMatchSignal(),
    MathConsistencySignal(),
    ExtractionCompletenessSignal(),
    DocumentQualitySignal(),
]

__all__ = ["ALL_SIGNALS"]
