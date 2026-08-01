"""Validation result and report schemas."""

from enum import Enum

from pydantic import BaseModel, Field


class ValidationStatus(str, Enum):
    """Outcome of a single validation rule."""

    PASS = "pass"
    FAIL = "fail"
    WARN = "warn"
    SKIP = "skip"


class ValidationResult(BaseModel):
    """Result from a single validation rule execution."""

    rule_name: str
    status: ValidationStatus
    message: str
    confidence_impact: float = 0.0  # negative = penalty
    suggested_fix: str | None = None


class ValidationReport(BaseModel):
    """Aggregated report of all validation results."""

    results: list[ValidationResult] = Field(default_factory=list)
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    skipped: int = 0

    @property
    def is_valid(self) -> bool:
        """True when no rules failed."""
        return self.failed == 0

    @property
    def total_confidence_impact(self) -> float:
        """Sum of all confidence impacts (typically negative)."""
        return sum(r.confidence_impact for r in self.results)
