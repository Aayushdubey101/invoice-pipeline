import hashlib
import json

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from invoice_pipeline.db import models
from invoice_pipeline.schemas import Document, DocumentStatus, PipelineError

log = structlog.get_logger()

_SCALAR_FIELDS = (
    "invoice_number", "invoice_date", "due_date", "buyer_name",
    "subtotal", "tax_amount", "total_amount", "currency",
    "payment_terms", "purchase_order",
)


async def persist(doc: Document, session: AsyncSession) -> Document:
    try:
        db_doc = await session.get(models.Document, doc.document_id)
        if db_doc is None:
            db_doc = models.Document(
                id=doc.document_id,
                filename=doc.filename,
                mime_type=doc.mime_type,
                file_size_bytes=len(doc.file_bytes),
                doc_type=doc.doc_type.value,
                status=doc.status.value,
                errors=[e.model_dump() for e in doc.errors],
            )
            session.add(db_doc)
        else:
            db_doc.doc_type = doc.doc_type.value
            db_doc.status = doc.status.value
            db_doc.errors = [e.model_dump() for e in doc.errors]

        if doc.extracted is not None:
            existing_inv = (await session.execute(
                select(models.Invoice).where(models.Invoice.document_id == doc.document_id)
            )).scalar_one_or_none()
            if existing_inv:
                await session.execute(
                    delete(models.InvoiceField).where(models.InvoiceField.invoice_id == existing_inv.id)
                )
                await session.execute(
                    delete(models.LineItem).where(models.LineItem.invoice_id == existing_inv.id)
                )
                await session.delete(existing_inv)
                await session.flush()

            canon = doc.canonicalized

            invoice_row = models.Invoice(
                document_id=doc.document_id,
                invoice_number=doc.extracted.invoice_number.value,
                invoice_date=canon.invoice_date.isoformat() if canon and canon.invoice_date else None,
                due_date=canon.due_date.isoformat() if canon and canon.due_date else None,
                buyer_name=doc.extracted.buyer_name.value,
                subtotal=canon.subtotal if canon else None,
                tax_amount=canon.tax_amount if canon else None,
                total_amount=canon.total_amount if canon else None,
                currency=canon.currency if canon else doc.extracted.currency.value,
                payment_terms=doc.extracted.payment_terms.value,
                purchase_order=doc.extracted.purchase_order.value,
                needs_review=canon.needs_review if canon else False,
                review_reasons=canon.review_reasons if canon else [],
                raw_extraction=doc.extracted.model_dump(),
            )
            session.add(invoice_row)
            await session.flush()

            fields = _build_field_rows(invoice_row.id, doc)
            session.add_all(fields)

            line_item_rows = _build_line_item_rows(invoice_row.id, doc)
            session.add_all(line_item_rows)

        audit = models.AuditLog(
            document_id=doc.document_id,
            actor="system",
            stage="persist",
            action="upsert",
            after_hash=hashlib.sha256(
                json.dumps(doc.extracted.model_dump() if doc.extracted else {}, sort_keys=True).encode()
            ).hexdigest(),
            extra={"errors": len(doc.errors)},
        )
        session.add(audit)

        await session.commit()

        final_status = _compute_status(doc)
        log.info(
            "pipeline_stage",
            stage="persist",
            document_id=doc.document_id,
            status=final_status.value,
        )
        return doc.model_copy(update={"status": final_status})

    except Exception as exc:
        await session.rollback()
        log.error("pipeline_stage_error", stage="persist", document_id=doc.document_id, error=str(exc))
        error = PipelineError(stage="persist", message=str(exc))
        return doc.model_copy(update={"errors": [*doc.errors, error], "status": DocumentStatus.FAILED})


def _compute_status(doc: Document) -> DocumentStatus:
    fatal_errors = [e for e in doc.errors if getattr(e, "fatal", True)]
    if fatal_errors:
        return DocumentStatus.FAILED
    if doc.canonicalized and doc.canonicalized.needs_review:
        return DocumentStatus.NEEDS_REVIEW
    return DocumentStatus.COMPLETE


def _build_field_rows(invoice_id: str, doc: Document) -> list[models.InvoiceField]:
    from invoice_pipeline.config import settings

    rows = []
    if doc.extracted is None:
        return rows
    for field_name in _SCALAR_FIELDS:
        fv = getattr(doc.extracted, field_name, None)
        if fv is None:
            continue
        rows.append(
            models.InvoiceField(
                invoice_id=invoice_id,
                field_name=field_name,
                raw_value=fv.value,
                confidence=float(fv.confidence),
                evidence=fv.evidence,
                needs_review=fv.confidence < settings.LOW_CONFIDENCE_THRESHOLD,
            )
        )
    return rows


def _build_line_item_rows(invoice_id: str, doc: Document) -> list[models.LineItem]:
    rows = []
    if doc.extracted is None:
        return rows
    for i, li in enumerate(doc.extracted.line_items):
        rows.append(
            models.LineItem(
                invoice_id=invoice_id,
                position=i,
                description_raw=li.description.value,
                quantity_raw=li.quantity.value,
                unit_price_raw=li.unit_price.value,
                total_raw=li.total.value,
                description_confidence=float(li.description.confidence),
                quantity_confidence=float(li.quantity.confidence),
                unit_price_confidence=float(li.unit_price.confidence),
                total_confidence=float(li.total.confidence),
            )
        )
    return rows
