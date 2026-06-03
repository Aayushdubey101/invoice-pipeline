"""
Generate synthetic invoice PDFs for demo/testing.

Usage:
    cd apps/api
    uv run python scripts/generate_synthetic_invoices.py
    uv run python scripts/generate_synthetic_invoices.py --output-dir /path/to/dir
"""

import argparse
import io
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import (
        HRFlowable,
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
except ImportError as exc:
    raise SystemExit(
        "reportlab not installed. Run: uv add --dev reportlab"
    ) from exc


@dataclass
class LineItemData:
    description: str
    quantity: float
    unit_price: float

    @property
    def total(self) -> float:
        return self.quantity * self.unit_price


@dataclass
class InvoiceData:
    filename: str
    vendor_name: str
    vendor_address: str
    buyer_name: str
    buyer_address: str
    invoice_number: str
    invoice_date: date
    due_date: date
    currency: str
    line_items: list[LineItemData]
    payment_terms: str = "Net 30"
    vendor_tax_id: str = ""
    tax_rate: float = 0.0
    po_number: str = ""
    notes: str = ""


_INVOICES: list[InvoiceData] = [
    InvoiceData(
        filename="acme_corp_inv_2024_001.pdf",
        vendor_name="Acme Corp",
        vendor_address="123 Main St, Springfield, IL 62701\nEIN: 12-3456789",
        buyer_name="TechCorp International",
        buyer_address="500 Business Park Dr, Chicago, IL 60601",
        invoice_number="ACM-2024-001",
        invoice_date=date(2024, 1, 15),
        due_date=date(2024, 2, 14),
        currency="USD",
        vendor_tax_id="12-3456789",
        tax_rate=0.08,
        payment_terms="Net 30",
        po_number="PO-2024-5001",
        line_items=[
            LineItemData("Software Development Services", 40, 150.00),
            LineItemData("Code Review", 8, 200.00),
            LineItemData("Technical Documentation", 5, 100.00),
        ],
    ),
    InvoiceData(
        filename="acme_corporation_inv_2024_002.pdf",
        vendor_name="ACME Corporation",
        vendor_address="123 Main Street, Springfield, IL 62701",
        buyer_name="TechCorp International",
        buyer_address="500 Business Park Dr, Chicago, IL 60601",
        invoice_number="ACM-2024-002",
        invoice_date=date(2024, 2, 20),
        due_date=date(2024, 3, 21),
        currency="USD",
        vendor_tax_id="12-3456789",
        tax_rate=0.08,
        payment_terms="Net 30",
        line_items=[
            LineItemData("API Integration Consulting", 20, 175.00),
            LineItemData("Infrastructure Setup", 1, 800.00),
        ],
    ),
    InvoiceData(
        filename="beta_inc_inv_2024_003.pdf",
        vendor_name="Beta Inc",
        vendor_address="456 Oak Ave, Portland, OR 97201\nEIN: 98-7654321",
        buyer_name="Startup Ventures LLC",
        buyer_address="100 Innovation Way, San Francisco, CA 94105",
        invoice_number="BETA-2024-0042",
        invoice_date=date(2024, 3, 1),
        due_date=date(2024, 3, 31),
        currency="USD",
        vendor_tax_id="98-7654321",
        tax_rate=0.0,
        payment_terms="Due on Receipt",
        line_items=[
            LineItemData("Monthly SaaS Platform License", 1, 4500.00),
        ],
    ),
    InvoiceData(
        filename="beta_incorporated_inv_2024_004.pdf",
        vendor_name="Beta Incorporated",
        vendor_address="456 Oak Avenue, Portland, Oregon 97201",
        buyer_name="Startup Ventures LLC",
        buyer_address="100 Innovation Way, San Francisco, CA 94105",
        invoice_number="BETA-2024-0043",
        invoice_date=date(2024, 4, 1),
        due_date=date(2024, 4, 30),
        currency="USD",
        tax_rate=0.0,
        payment_terms="Due on Receipt",
        line_items=[
            LineItemData("SaaS Platform License", 1, 4500.00),
            LineItemData("Priority Support Package", 1, 500.00),
            LineItemData("Onboarding Sessions", 3, 200.00),
        ],
    ),
    InvoiceData(
        filename="gamma_services_cloud_2024_005.pdf",
        vendor_name="Gamma Services LLC",
        vendor_address="789 Pine Rd, Austin, TX 78701\nEIN: 55-1234567",
        buyer_name="MegaCorp Solutions",
        buyer_address="1000 Corporate Blvd, Dallas, TX 75201",
        invoice_number="GS-INV-2024-0123",
        invoice_date=date(2024, 5, 1),
        due_date=date(2024, 5, 31),
        currency="USD",
        vendor_tax_id="55-1234567",
        tax_rate=0.0,
        payment_terms="Net 30",
        line_items=[
            LineItemData("Cloud Compute (us-east-1) - 720 hrs", 720, 0.12),
            LineItemData("Storage - 500 GB/mo", 500, 0.023),
            LineItemData("Data Transfer Out - 120 GB", 120, 0.09),
            LineItemData("Managed Database (db.t3.medium)", 1, 65.00),
        ],
    ),
    InvoiceData(
        filename="delta_solutions_equipment_2024_006.pdf",
        vendor_name="Delta Solutions",
        vendor_address="321 Elm Blvd, Seattle, WA 98101",
        buyer_name="Enterprise Corp",
        buyer_address="2000 Tech Campus, Bellevue, WA 98004",
        invoice_number="DS-2024-INV-789",
        invoice_date=date(2024, 6, 10),
        due_date=date(2024, 7, 10),
        currency="USD",
        tax_rate=0.10,
        payment_terms="Net 30",
        po_number="PO-ENT-2024-8900",
        line_items=[
            LineItemData("Dell PowerEdge R750 Server", 4, 3200.00),
            LineItemData("32GB DDR4 RAM Module", 16, 180.00),
            LineItemData("1TB NVMe SSD", 8, 220.00),
            LineItemData("Installation & Configuration", 1, 1500.00),
        ],
    ),
    InvoiceData(
        filename="epsilon_technology_saas_2024_007.pdf",
        vendor_name="Epsilon Technology",
        vendor_address="654 Maple Dr, Boston, MA 02101\nVAT: GB123456789",
        buyer_name="Global Enterprises GmbH",
        buyer_address="Hauptstrasse 15, 10115 Berlin, Germany",
        invoice_number="EPS-2024-UK-0056",
        invoice_date=date(2024, 7, 1),
        due_date=date(2024, 7, 31),
        currency="EUR",
        tax_rate=0.20,
        payment_terms="Net 30",
        line_items=[
            LineItemData("Enterprise Analytics Platform - Annual", 1, 8500.00),
            LineItemData("API Access (Premium Tier)", 1, 1200.00),
            LineItemData("Professional Services - 10 hrs", 10, 150.00),
        ],
    ),
    InvoiceData(
        filename="incomplete_messy_invoice_008.pdf",
        vendor_name="XYZ Consulting",
        vendor_address="Unknown Address",
        buyer_name="",
        buyer_address="",
        invoice_number="",
        invoice_date=date(2024, 8, 15),
        due_date=date(2024, 9, 15),
        currency="USD",
        tax_rate=0.0,
        payment_terms="",
        notes="DRAFT - DO NOT PAY",
        line_items=[
            LineItemData("Consulting Services", 1, 2500.00),
        ],
    ),
    InvoiceData(
        filename="unknown_vendor_new_2024_009.pdf",
        vendor_name="Zeta Analytics Partners",
        vendor_address="99 Data Science Ave, Mountain View, CA 94043",
        buyer_name="TechCorp International",
        buyer_address="500 Business Park Dr, Chicago, IL 60601",
        invoice_number="ZAP-2024-001",
        invoice_date=date(2024, 9, 1),
        due_date=date(2024, 10, 1),
        currency="USD",
        tax_rate=0.08,
        payment_terms="Net 30",
        line_items=[
            LineItemData("Data Analysis Report Q3", 1, 3200.00),
            LineItemData("Dashboard Development", 40, 125.00),
        ],
    ),
    InvoiceData(
        filename="delta_large_order_2024_010.pdf",
        vendor_name="Delta Solutions Inc",
        vendor_address="321 Elm Blvd, Seattle, WA 98101",
        buyer_name="MegaCorp Solutions",
        buyer_address="1000 Corporate Blvd, Dallas, TX 75201",
        invoice_number="DS-2024-INV-999",
        invoice_date=date(2024, 10, 1),
        due_date=date(2024, 10, 31),
        currency="USD",
        tax_rate=0.10,
        payment_terms="Net 30",
        po_number="PO-MEGA-2024-1100",
        line_items=[
            LineItemData("HP ProBook 450 G10 Laptop", 25, 899.00),
            LineItemData("Dell 27\" 4K Monitor", 25, 450.00),
            LineItemData("Logitech MX Keys Keyboard", 25, 99.00),
            LineItemData("Logitech MX Master 3 Mouse", 25, 79.00),
            LineItemData("USB-C Docking Station", 25, 149.00),
            LineItemData("Extended Warranty - 3yr", 25, 129.00),
            LineItemData("IT Setup & Deployment", 25, 45.00),
        ],
    ),
    InvoiceData(
        filename="acme_corp_gbp_2024_011.pdf",
        vendor_name="Acme Corp",
        vendor_address="123 Main St, Springfield, IL 62701",
        buyer_name="British Holdings Ltd",
        buyer_address="10 Canary Wharf, London E14 5AB, UK",
        invoice_number="ACM-2024-UK-011",
        invoice_date=date(2024, 11, 1),
        due_date=date(2024, 12, 1),
        currency="GBP",
        tax_rate=0.0,
        payment_terms="Net 30",
        line_items=[
            LineItemData("UK Market Analysis Report", 1, 2800.00),
            LineItemData("Strategic Consulting - 15 hrs", 15, 220.00),
        ],
    ),
    InvoiceData(
        filename="gamma_services_annual_2024_012.pdf",
        vendor_name="Gamma LLC",
        vendor_address="789 Pine Road, Austin, Texas 78701",
        buyer_name="StartupCo",
        buyer_address="50 Venture St, New York, NY 10001",
        invoice_number="GS-2024-ANNUAL-001",
        invoice_date=date(2024, 12, 1),
        due_date=date(2025, 1, 1),
        currency="USD",
        vendor_tax_id="55-1234567",
        tax_rate=0.08,
        payment_terms="Net 30",
        line_items=[
            LineItemData("Annual Cloud Infrastructure - Base", 1, 15000.00),
            LineItemData("Premium Support SLA", 1, 3600.00),
            LineItemData("Security & Compliance Audit", 1, 2500.00),
            LineItemData("Training Credits", 10, 200.00),
        ],
    ),
]


def _currency_symbol(code: str) -> str:
    return {"USD": "$", "EUR": "€", "GBP": "£", "INR": "₹"}.get(code, code + " ")


def _fmt(amount: float, currency: str) -> str:
    sym = _currency_symbol(currency)
    return f"{sym}{amount:,.2f}"


def generate_invoice_pdf(inv: InvoiceData) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    bold = ParagraphStyle("bold", parent=styles["Normal"], fontName="Helvetica-Bold")
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9)
    title_style = ParagraphStyle(
        "title", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=18
    )
    heading2 = ParagraphStyle(
        "heading2", parent=styles["Normal"], fontName="Helvetica-Bold", fontSize=11
    )

    story = []

    # Header: INVOICE + invoice number
    header_data = [
        [
            Paragraph("INVOICE", title_style),
            Paragraph(
                f"<b>Invoice #:</b> {inv.invoice_number or 'N/A'}<br/>"
                f"<b>Date:</b> {inv.invoice_date.isoformat()}<br/>"
                f"<b>Due:</b> {inv.due_date.isoformat()}",
                styles["Normal"],
            ),
        ]
    ]
    header_table = Table(header_data, colWidths=[4 * inch, 3 * inch])
    header_table.setStyle(
        TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 0.2 * inch))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
    story.append(Spacer(1, 0.2 * inch))

    # Vendor + Buyer addresses
    from_text = f"<b>From:</b><br/>{inv.vendor_name}<br/>{inv.vendor_address.replace(chr(10), '<br/>')}"
    if inv.vendor_tax_id:
        from_text += f"<br/>Tax ID: {inv.vendor_tax_id}"

    to_text = f"<b>Bill To:</b><br/>"
    if inv.buyer_name:
        to_text += f"{inv.buyer_name}<br/>"
    if inv.buyer_address:
        to_text += inv.buyer_address.replace("\n", "<br/>")

    addr_data = [
        [Paragraph(from_text, styles["Normal"]), Paragraph(to_text, styles["Normal"])]
    ]
    addr_table = Table(addr_data, colWidths=[3.5 * inch, 3.5 * inch])
    addr_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(addr_table)

    if inv.po_number:
        story.append(Spacer(1, 0.15 * inch))
        story.append(Paragraph(f"PO Number: {inv.po_number}", styles["Normal"]))

    story.append(Spacer(1, 0.25 * inch))

    # Line items table
    col_headers = ["Description", "Qty", "Unit Price", "Total"]
    table_data: list[list[str]] = [col_headers]

    subtotal = 0.0
    for item in inv.line_items:
        table_data.append([
            item.description,
            str(int(item.quantity)) if item.quantity == int(item.quantity) else f"{item.quantity}",
            _fmt(item.unit_price, inv.currency),
            _fmt(item.total, inv.currency),
        ])
        subtotal += item.total

    tax_amount = subtotal * inv.tax_rate
    total = subtotal + tax_amount

    # Summary rows
    table_data.append(["", "", "Subtotal:", _fmt(subtotal, inv.currency)])
    if inv.tax_rate > 0:
        table_data.append([
            "",
            "",
            f"Tax ({int(inv.tax_rate * 100)}%):",
            _fmt(tax_amount, inv.currency),
        ])
    table_data.append(["", "", "TOTAL DUE:", _fmt(total, inv.currency)])

    n_items = len(inv.line_items)
    items_table = Table(
        table_data,
        colWidths=[3.5 * inch, 0.6 * inch, 1.2 * inch, 1.2 * inch],
    )
    items_table.setStyle(
        TableStyle([
            # Header row
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ("ALIGN", (0, 0), (0, -1), "LEFT"),
            ("GRID", (0, 0), (-1, n_items), 0.5, colors.HexColor("#cccccc")),
            ("ROWBACKGROUNDS", (0, 1), (-1, n_items), [colors.white, colors.HexColor("#f8f9fa")]),
            ("FONTNAME", (0, 1), (-1, n_items), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, n_items), 9),
            # Summary rows
            ("FONTNAME", (2, n_items + 1), (2, -1), "Helvetica-Bold"),
            ("LINEABOVE", (2, n_items + 1), (-1, n_items + 1), 1, colors.black),
            # Total row highlight
            ("BACKGROUND", (2, -1), (-1, -1), colors.HexColor("#2c3e50")),
            ("TEXTCOLOR", (2, -1), (-1, -1), colors.white),
            ("FONTNAME", (2, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (2, -1), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    story.append(items_table)
    story.append(Spacer(1, 0.25 * inch))

    # Footer
    footer_parts = []
    if inv.payment_terms:
        footer_parts.append(f"<b>Payment Terms:</b> {inv.payment_terms}")
    footer_parts.append(f"<b>Currency:</b> {inv.currency}")
    if inv.notes:
        footer_parts.append(f"<b>Notes:</b> {inv.notes}")

    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 0.1 * inch))
    story.append(Paragraph("  |  ".join(footer_parts), small))

    doc.build(story)
    return buffer.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic invoice PDFs")
    parser.add_argument(
        "--output-dir",
        default="tests/fixtures/synthetic",
        help="Directory to write PDFs (default: tests/fixtures/synthetic)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = 0
    for inv in _INVOICES:
        out_path = output_dir / inv.filename
        if out_path.exists():
            print(f"  skip (exists): {inv.filename}")
            continue
        pdf_bytes = generate_invoice_pdf(inv)
        out_path.write_bytes(pdf_bytes)
        print(f"  generated: {inv.filename} ({len(pdf_bytes):,} bytes)")
        generated += 1

    print(f"\nDone: {generated} invoice(s) written to {output_dir}")


if __name__ == "__main__":
    main()
