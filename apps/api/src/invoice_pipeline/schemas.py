from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from invoice_pipeline.db.models import LEGACY_WORKSPACE_ID

if TYPE_CHECKING:
    pass


class RowType(str, Enum):
    """Semantic row classification for line items."""

    ITEM = "item"           # Normal product / service line
    DISCOUNT = "discount"   # Discount row (negative amount)
    TAX = "tax"             # Tax row within table
    SUBTOTAL = "subtotal"   # Subtotal row
    TOTAL = "total"         # Grand total row inside table
    SHIPPING = "shipping"   # Shipping / freight row
    HEADER = "header"       # Continuation header (multi-page)
    UNKNOWN = "unknown"


class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETE = "complete"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


class DocumentType(str, Enum):
    TEXT_PDF = "text_pdf"
    SCANNED_PDF = "scanned_pdf"
    IMAGE = "image"
    EMAIL = "email"
    UNKNOWN = "unknown"


class VendorStatus(str, Enum):
    ACTIVE = "active"
    PENDING_REVIEW = "pending_review"
    INACTIVE = "inactive"


# ── LLM extraction schemas ────────────────────────────────────────────────────


class FieldValue(BaseModel):
    value: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str | None = None  # verbatim source snippet
    page: int | None = None
    bbox: list[float] | None = None  # [x0, y0, x1, y1]


class CellValue(BaseModel):
    """Rich field value with spatial provenance metadata."""

    value: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence: str | None = None     # verbatim source snippet
    page: int | None = None          # 0-indexed page number
    bbox: list[float] | None = None  # [x0, y0, x1, y1]
    source_evidence: str | None = None  # broader context block from OCR/text


class LineItem(BaseModel):
    """LLM extraction target for line items — each cell is a FieldValue."""

    description: FieldValue = Field(default_factory=FieldValue)
    quantity: FieldValue = Field(default_factory=FieldValue)
    unit_price: FieldValue = Field(default_factory=FieldValue)
    total: FieldValue = Field(default_factory=FieldValue)


class RichLineItem(BaseModel):
    """Phase-4 rich line item with per-cell spatial metadata and row classification."""

    description: CellValue = Field(default_factory=CellValue)
    quantity: CellValue = Field(default_factory=CellValue)
    unit_price: CellValue = Field(default_factory=CellValue)
    total: CellValue = Field(default_factory=CellValue)
    row_type: RowType = RowType.ITEM
    math_valid: bool | None = None   # qty * unit_price ≈ total?
    page: int | None = None          # primary page this row appears on
    table_index: int = 0             # which table on the page (0-indexed)


class Invoice(BaseModel):
    """LLM extraction target. Every field has value|null + confidence + evidence."""

    invoice_number: FieldValue = Field(default_factory=FieldValue)
    invoice_date: FieldValue = Field(default_factory=FieldValue)
    due_date: FieldValue = Field(default_factory=FieldValue)
    vendor_name: FieldValue = Field(default_factory=FieldValue)
    vendor_address: FieldValue = Field(default_factory=FieldValue)
    vendor_tax_id: FieldValue = Field(default_factory=FieldValue)
    buyer_name: FieldValue = Field(default_factory=FieldValue)
    buyer_address: FieldValue = Field(default_factory=FieldValue)
    subtotal: FieldValue = Field(default_factory=FieldValue)
    tax_amount: FieldValue = Field(default_factory=FieldValue)
    total_amount: FieldValue = Field(default_factory=FieldValue)
    currency: FieldValue = Field(default_factory=FieldValue)
    payment_terms: FieldValue = Field(default_factory=FieldValue)
    purchase_order: FieldValue = Field(default_factory=FieldValue)
    line_items: list[LineItem] = Field(default_factory=list)
    rich_line_items: list[RichLineItem] = Field(default_factory=list)


# ── Canonicalized output ──────────────────────────────────────────────────────


class CanonicalizedInvoice(BaseModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    vendor_id: str | None = None
    buyer_name: str | None = None
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    total_amount: Decimal | None = None
    currency: str | None = None  # ISO 4217
    payment_terms: str | None = None
    purchase_order: str | None = None
    raw: Invoice  # always keep original LLM output
    needs_review: bool = False
    review_reasons: list[str] = Field(default_factory=list)


# ── Pipeline internal models ──────────────────────────────────────────────────


class Word(BaseModel):
    text: str
    bbox: tuple[float, float, float, float] | None = None
    page: int = 0
    confidence: float = 1.0


class Page(BaseModel):
    page_num: int
    text: str
    words: list[Word] = Field(default_factory=list)


class PipelineError(BaseModel):
    stage: str
    message: str
    detail: str | None = None
    fatal: bool = True


class Document(BaseModel):
    document_id: str  # SHA256 hex, salted with workspace_id
    workspace_id: str = LEGACY_WORKSPACE_ID
    filename: str
    mime_type: str
    file_bytes: bytes = Field(default=b"", exclude=True)
    doc_type: DocumentType = DocumentType.UNKNOWN
    pages: list[Page] = Field(default_factory=list)
    raw_text: str = ""
    extracted: Invoice | None = None
    canonicalized: CanonicalizedInvoice | None = None
    errors: list[PipelineError] = Field(default_factory=list)
    status: DocumentStatus = DocumentStatus.PENDING
    parent_document_id: str | None = None  # for email attachments
    vendor_matched: bool = False
    validation_report: dict[str, Any] | None = None  # ValidationReport.model_dump()
    confidence_breakdown: dict[str, Any] | None = None  # ConfidenceBreakdown.model_dump_summary()


# ── API response schemas ──────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str


class LLMStatusResponse(BaseModel):
    provider: str
    model: str
    endpoint: str | None = None


class ProblemDetail(BaseModel):
    """RFC 7807 problem details."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None
