from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

class ConfidenceSignal(BaseModel):
    name: str
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    description: str

class ConfidenceBreakdown(BaseModel):
    signals: list[ConfidenceSignal] = Field(default_factory=list)

    @property
    def overall_confidence(self) -> float:
        if not self.signals:
            return 0.0
        total_weight = sum(s.weight for s in self.signals)
        if total_weight == 0:
            return 0.0
        weighted_sum = sum(s.score * s.weight for s in self.signals)
        return weighted_sum / total_weight

    @property
    def needs_review(self) -> bool:
        return self.overall_confidence < 0.75

    def model_dump_summary(self) -> dict[str, float]:
        summary = {"overall": round(self.overall_confidence, 2)}
        for sig in self.signals:
            summary[sig.name] = round(sig.score, 2)
        return summary
