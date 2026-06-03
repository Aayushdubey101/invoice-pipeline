"""
Process synthetic invoice PDFs through the pipeline.

Usage:
    cd apps/api
    uv run python scripts/seed_invoices.py
    uv run python scripts/seed_invoices.py --fixtures-dir /path/to/pdfs --api-url http://localhost:8000
"""

import argparse
import asyncio
import mimetypes
from pathlib import Path

import httpx
import structlog

log = structlog.get_logger()


async def seed(fixtures_dir: Path, api_url: str) -> None:
    pdfs = sorted(fixtures_dir.glob("*.pdf"))
    if not pdfs:
        log.warning("no_pdfs_found", dir=str(fixtures_dir))
        return

    log.info("seeding_invoices", count=len(pdfs), api=api_url)

    async with httpx.AsyncClient(base_url=api_url, timeout=120.0) as client:
        ok = 0
        failed = 0
        skipped = 0
        for pdf_path in pdfs:
            mime = mimetypes.guess_type(pdf_path.name)[0] or "application/pdf"
            try:
                pdf_bytes = pdf_path.read_bytes()
                response = await client.post(
                    "/documents/upload",
                    files={"file": (pdf_path.name, pdf_bytes, mime)},
                )
                data = response.json()

                if response.status_code == 202:
                    status = data.get("status", "?")
                    errors = data.get("errors", [])
                    doc_id = data.get("document_id", "?")[:12]
                    if status == "duplicate":
                        log.info("invoice_skipped", file=pdf_path.name, doc_id=doc_id)
                        skipped += 1
                    else:
                        log.info(
                            "invoice_processed",
                            file=pdf_path.name,
                            doc_id=doc_id,
                            status=status,
                            error_count=len(errors),
                        )
                        ok += 1
                else:
                    log.warning(
                        "invoice_upload_failed",
                        file=pdf_path.name,
                        status_code=response.status_code,
                        detail=data,
                    )
                    failed += 1
            except Exception as exc:
                log.error("invoice_error", file=pdf_path.name, error=str(exc))
                failed += 1

    log.info(
        "seed_complete",
        processed=ok,
        skipped=skipped,
        failed=failed,
        total=len(pdfs),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed invoice PDFs via pipeline API")
    parser.add_argument(
        "--fixtures-dir",
        default="tests/fixtures/synthetic",
        help="Directory containing invoice PDFs",
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="Base URL of the invoice pipeline API",
    )
    args = parser.parse_args()

    fixtures_dir = Path(args.fixtures_dir)
    if not fixtures_dir.exists():
        raise SystemExit(
            f"Fixtures dir not found: {fixtures_dir}\n"
            "Run generate_synthetic_invoices.py first."
        )

    asyncio.run(seed(fixtures_dir, args.api_url))


if __name__ == "__main__":
    main()
