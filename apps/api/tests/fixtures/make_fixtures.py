"""
Run once to generate test fixtures:
  uv run python tests/fixtures/make_fixtures.py
"""

import struct
import zlib
from pathlib import Path

HERE = Path(__file__).parent


# ── Text PDF ──────────────────────────────────────────────────────────────────


def _make_text_pdf(path: Path) -> None:
    content = b"""\
%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 612 792]/Parent 2 0 R/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj
4 0 obj<</Length 406>>
stream
BT
/F1 12 Tf
50 750 Td (INVOICE) Tj
0 -20 Td (Invoice Number: INV-2024-001) Tj
0 -20 Td (Invoice Date: 2024-01-15) Tj
0 -20 Td (Due Date: 2024-02-15) Tj
0 -20 Td (Vendor: Acme Corp) Tj
0 -20 Td (Buyer: Beta Inc) Tj
0 -20 Td (Description: Consulting Services) Tj
0 -20 Td (Quantity: 10  Unit Price: $100.00  Total: $1000.00) Tj
0 -20 Td (Subtotal: $1000.00) Tj
0 -20 Td (Tax: $100.00) Tj
0 -20 Td (Total Amount: $1100.00 USD) Tj
0 -20 Td (Payment Terms: Net 30) Tj
ET
endstream
endobj
5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000724 00000 n
trailer<</Size 6/Root 1 0 R>>
startxref
805
%%EOF"""
    path.write_bytes(content)
    print(f"Written: {path}")


# ── Minimal PNG (1x1 white pixel) ─────────────────────────────────────────────


def _make_png(path: Path) -> None:
    def _chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    raw = b"\x00\xff\xff\xff"  # filter byte + RGB white
    idat = zlib.compress(raw)

    png = b"\x89PNG\r\n\x1a\n"
    png += _chunk(b"IHDR", ihdr)
    png += _chunk(b"IDAT", idat)
    png += _chunk(b"IEND", b"")
    path.write_bytes(png)
    print(f"Written: {path}")


# ── Scanned PDF (PDF wrapping a PNG image, no text layer) ─────────────────────


def _make_scanned_pdf(path: Path) -> None:
    """PDF containing only an embedded image — no extractable text."""

    # Tiny 1x1 white PNG
    def _chunk(name: bytes, data: bytes) -> bytes:
        c = name + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0)
    raw_rows = b"".join(b"\x00" + b"\xff\xff\xff" * 8 for _ in range(8))
    idat = zlib.compress(raw_rows)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")
    )

    # Minimal PDF with image XObject — no text operators
    pdf = b"""%PDF-1.4
1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj
2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj
3 0 obj<</Type/Page/MediaBox[0 0 100 100]/Parent 2 0 R/Contents 4 0 R/Resources<</XObject<</Im1 5 0 R>>>>>>endobj
4 0 obj<</Length 32>>
stream
q 100 0 0 100 0 0 cm /Im1 Do Q
endstream
endobj
"""
    img_len = len(png_bytes)
    pdf += (
        f"5 0 obj<</Type/XObject/Subtype/Image/Width 8/Height 8/ColorSpace/DeviceRGB"
        f"/BitsPerComponent 8/Filter/FlateDecode/Length {img_len}>>\n"
        f"stream\n"
    ).encode()
    pdf += png_bytes
    pdf += b"\nendstream\nendobj\n"
    pdf += b"xref\n0 6\n0000000000 65535 f \n"
    pdf += b"trailer<</Size 6/Root 1 0 R>>\nstartxref\n9\n%%EOF"
    path.write_bytes(pdf)
    print(f"Written: {path}")


# ── .eml with plain text invoice ─────────────────────────────────────────────


def _make_eml(path: Path) -> None:
    eml = b"""\
MIME-Version: 1.0
From: vendor@acme.com
To: accounting@beta.com
Subject: Invoice INV-2024-002 from Acme Corp
Content-Type: text/plain; charset=utf-8

Dear Beta Inc,

Please find below invoice details:

Invoice Number: INV-2024-002
Invoice Date: 2024-02-01
Due Date: 2024-03-01
Vendor: Acme Corp
Buyer: Beta Inc
Total Amount: $2200.00 USD
Tax: $200.00
Subtotal: $2000.00
Payment Terms: Net 30

Thank you for your business.
Acme Corp
"""
    path.write_bytes(eml)
    print(f"Written: {path}")


if __name__ == "__main__":
    HERE.mkdir(parents=True, exist_ok=True)
    _make_text_pdf(HERE / "sample_invoice.pdf")
    _make_text_pdf(HERE / "sample_invoice_2.pdf")
    _make_scanned_pdf(HERE / "scanned_invoice.pdf")
    _make_png(HERE / "invoice_image.png")
    _make_eml(HERE / "invoice_email.eml")
    print("Done.")
