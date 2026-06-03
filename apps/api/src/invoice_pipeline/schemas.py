from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


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


class LineItem(BaseModel):
    description: FieldValue = Field(default_factory=FieldValue)
    quantity: FieldValue = Field(default_factory=FieldValue)
    unit_price: FieldValue = Field(default_factory=FieldValue)
    total: FieldValue = Field(default_factory=FieldValue)


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
    document_id: str  # SHA256 hex
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
