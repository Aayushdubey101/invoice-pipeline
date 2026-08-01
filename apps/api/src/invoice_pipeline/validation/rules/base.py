"""Abstract base class for all validation rules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.schemas import Document, Invoice
from invoice_pipeline.validation.models import ValidationResult


@dataclass
class ValidationContext:
    """Shared context passed to every validation rule.

    Carries the full Document, raw text, and optional DB session
    (needed by rules that query the database, e.g. duplicate detection).
    """

    document: Document
    raw_text: str = ""
    session: AsyncSession | None = None
    extra: dict[str, object] = field(default_factory=dict)


class BaseRule(ABC):
    """Abstract base for a single validation rule.

    Subclasses must set ``name`` and ``description`` and implement ``validate``.
    Rules must NEVER raise — return SKIP on unexpected conditions.
    """

    name: str
    description: str

    @abstractmethod
    async def validate(
        self,
        invoice: Invoice,
        context: ValidationContext,
    ) -> ValidationResult:
        """Run the validation logic and return a result."""
        ...
