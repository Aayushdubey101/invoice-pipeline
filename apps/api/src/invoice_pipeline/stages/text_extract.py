import io

import structlog

from invoice_pipeline.schemas import Document, DocumentType, Page, PipelineError, Word

log = structlog.get_logger()


async def text_extract(doc: Document) -> Document:
    try:
        if doc.doc_type == DocumentType.EMAIL:
            pages = _extract_email(doc.file_bytes)
        elif doc.doc_type in (DocumentType.TEXT_PDF, DocumentType.SCANNED_PDF):
            pages = _extract_pdf(doc.file_bytes)
        elif doc.doc_type in (DocumentType.IMAGE,):
            return doc  # handled by ocr_fallback stage
        else:
            pages = _extract_plain(doc.file_bytes)

        raw_text = "\n\n".join(p.text for p in pages)
        log.info(
            "pipeline_stage",
            stage="text_extract",
            document_id=doc.document_id,
            pages=len(pages),
            chars=len(raw_text),
        )
        return doc.model_copy(update={"pages": pages, "raw_text": raw_text})
    except Exception as exc:
        log.error(
            "pipeline_stage_error",
            stage="text_extract",
            document_id=doc.document_id,
            error=str(exc),
        )
        error = PipelineError(stage="text_extract", message=str(exc))
        return doc.model_copy(update={"errors": [*doc.errors, error]})


def _extract_pdf(file_bytes: bytes) -> list[Page]:
    pages: list[Page] = []

    try:
        import pdfplumber

        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                words: list[Word] = []
                for w in page.extract_words() or []:
                    words.append(
                        Word(
                            text=w["text"],
                            bbox=(w["x0"], w["top"], w["x1"], w["bottom"]),
                            page=i,
                        )
                    )
                pages.append(Page(page_num=i, text=text, words=words))

        if all(len(p.text) < 10 for p in pages):
            return _extract_pdf_pymupdf(file_bytes)

        return pages
    except Exception:
        return _extract_pdf_pymupdf(file_bytes)


def _extract_pdf_pymupdf(file_bytes: bytes) -> list[Page]:
    import fitz  # PyMuPDF

    pages: list[Page] = []
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            text = page.get_text()
            pages.append(Page(page_num=i, text=text))
    return pages


def _extract_email(file_bytes: bytes) -> list[Page]:
    """Extract email body text. Attachment PDFs are handled as child documents in pipeline."""
    try:
        from unstructured.partition.email import partition_email

        elements = partition_email(file=io.BytesIO(file_bytes), paragraph_grouper=False)
        text = "\n".join(str(e) for e in elements)
        return [Page(page_num=0, text=text)]
    except Exception:
        # stdlib fallback
        return _extract_email_stdlib(file_bytes)


def _extract_email_stdlib(file_bytes: bytes) -> list[Page]:
    import email as email_lib

    msg = email_lib.message_from_bytes(file_bytes)
    parts: list[str] = []

    subject = msg.get("Subject", "")
    if subject:
        parts.append(f"Subject: {subject}")

    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "text/plain":
            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                parts.append(payload.decode("utf-8", errors="replace"))
        elif ct == "text/html":
            import html

            payload = part.get_payload(decode=True)
            if isinstance(payload, bytes):
                raw_html = payload.decode("utf-8", errors="replace")
                # strip tags for plain text approximation
                import re

                text = re.sub(r"<[^>]+>", " ", raw_html)
                parts.append(html.unescape(text))

    return [Page(page_num=0, text="\n".join(parts))]


def _extract_plain(file_bytes: bytes) -> list[Page]:
    text = file_bytes.decode("utf-8", errors="replace")
    return [Page(page_num=0, text=text)]
