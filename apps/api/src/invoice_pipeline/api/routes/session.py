"""Phase 14.6 — Finish Session.

Bundles the workspace's data as a PDF+Excel+JSON zip, streams it to the
caller, then purges every row and file belonging to the workspace — the
guest zero-retention "Finish Session" flow.
"""

import io
import json
import zipfile
from datetime import datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from invoice_pipeline.api.deps import get_current_workspace
from invoice_pipeline.api.limiter import limiter
from invoice_pipeline.api.routes.export import build_pdf_report, build_workbook
from invoice_pipeline.db import models
from invoice_pipeline.db.models import Workspace
from invoice_pipeline.db.session import get_session
from invoice_pipeline.services.workspace_lifecycle import purge_workspace_data

log = structlog.get_logger()
router = APIRouter()


def _build_json_report(invoices: list) -> bytes:
    payload: list[dict[str, Any]] = []
    for inv in invoices:
        payload.append(
            {
                "invoice_number": inv.invoice_number,
                "vendor": inv.vendor.canonical_name if inv.vendor else None,
                "invoice_date": inv.invoice_date,
                "due_date": inv.due_date,
                "currency": inv.currency,
                "subtotal": str(inv.subtotal) if inv.subtotal is not None else None,
                "tax_amount": str(inv.tax_amount) if inv.tax_amount is not None else None,
                "total_amount": str(inv.total_amount) if inv.total_amount is not None else None,
                "needs_review": inv.needs_review,
                "line_items": [
                    {
                        "description": li.description_raw,
                        "quantity": li.quantity_raw,
                        "unit_price": li.unit_price_raw,
                        "total": li.total_raw,
                    }
                    for li in sorted(inv.line_items, key=lambda x: x.position)
                ],
            }
        )
    return json.dumps(payload, indent=2).encode("utf-8")


@router.post("/finish")
@limiter.limit("5/minute")
async def finish_session(
    request: Request,
    session: AsyncSession = Depends(get_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> StreamingResponse:
    result = await session.execute(
        select(models.Invoice)
        .where(models.Invoice.workspace_id == workspace.id)
        .options(
            selectinload(models.Invoice.vendor),
            selectinload(models.Invoice.document),
            selectinload(models.Invoice.line_items),
        )
    )
    invoices = result.scalars().all()

    wb = build_workbook(invoices)
    excel_buf = io.BytesIO()
    wb.save(excel_buf)

    pdf_bytes = build_pdf_report(invoices)
    json_bytes = _build_json_report(invoices)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("invoices.xlsx", excel_buf.getvalue())
        zf.writestr("invoices.pdf", pdf_bytes)
        zf.writestr("invoices.json", json_bytes)
    zip_buf.seek(0)

    workspace_id = workspace.id
    record_count = len(invoices)

    await purge_workspace_data(workspace_id, session)

    log.info("session_finished", workspace_id=workspace_id, record_count=record_count)

    filename = f"session_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.zip"
    return StreamingResponse(
        zip_buf,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"; filename*=UTF-8\'\'{filename}',
        },
    )
