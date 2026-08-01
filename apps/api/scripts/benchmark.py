import argparse
import asyncio
import csv
import json
import logging
import random
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from invoice_pipeline.db.models import Base
from invoice_pipeline.llm.base import ExtractionMeta
from invoice_pipeline.pipeline import run_pipeline
from invoice_pipeline.schemas import FieldValue, Invoice
from scripts.generate_synthetic_invoices import _INVOICES, InvoiceData, generate_invoice_pdf


logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("benchmark")

BENCHMARK_DIR = Path("scripts/benchmarks")
BENCHMARK_DIR.mkdir(exist_ok=True, parents=True)
HISTORY_FILE = BENCHMARK_DIR / "history.json"
REPORT_MD = BENCHMARK_DIR / "report.md"
REPORT_CSV = BENCHMARK_DIR / "report.csv"

def init_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    return engine

async def setup_db(engine):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    return async_sessionmaker(engine, expire_on_commit=False)

def safe_decimal(d) -> Decimal:
    if d is None:
        return Decimal(0)
    return Decimal(str(d))

def compute_metrics(true_values, pred_values):
    """Computes Precision, Recall, F1 for boolean lists."""
    tp = sum(1 for t, p in zip(true_values, pred_values) if t and p)
    fp = sum(1 for t, p in zip(true_values, pred_values) if not t and p)
    fn = sum(1 for t, p in zip(true_values, pred_values) if t and not p)
    
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return precision, recall, f1, (tp + fn) # returns total trues

async def run_benchmark(use_mock_llm: bool = False):
    print("Initializing benchmark database...")
    engine = init_db()
    session_factory = await setup_db(engine)

    results = []
    
    print(f"Running pipeline on {len(_INVOICES)} synthetic invoices...")
    
    total = len(_INVOICES)
    
    metrics = {
        "vendor": [],
        "invoice_number": [],
        "date": [],
        "currency": [],
        "tax": [],
        "line_items": []
    }
    
    for i, inv_data in enumerate(_INVOICES):
        print(f"Processing {i+1}/{total}: {inv_data.filename}")
        pdf_bytes = generate_invoice_pdf(inv_data)
        
        # Build mock response if requested
        mock_provider = None
        if use_mock_llm:
            mock_provider = AsyncMock()
            
            # Simulate a 90% accurate extraction
            extracted_inv = Invoice(
                vendor_name=FieldValue(value=inv_data.vendor_name if random.random() > 0.1 else "Wrong Vendor", confidence=0.9),
                invoice_number=FieldValue(value=inv_data.invoice_number if random.random() > 0.1 else "INV-WRONG", confidence=0.9),
                invoice_date=FieldValue(value=inv_data.invoice_date.isoformat() if random.random() > 0.1 else "2020-01-01", confidence=0.9),
                due_date=FieldValue(value=inv_data.due_date.isoformat(), confidence=0.9),
                currency=FieldValue(value=inv_data.currency if random.random() > 0.1 else "CAD", confidence=0.9),
                subtotal=FieldValue(value="0", confidence=0.9),
                tax_amount=FieldValue(
                    value=str(Decimal(sum(item.total for item in inv_data.line_items) * inv_data.tax_rate).quantize(Decimal("0.01"))) if random.random() > 0.1 else "0.00",
                    confidence=0.9
                ),
                total_amount=FieldValue(value="0", confidence=0.9),
                buyer_name=FieldValue(value=inv_data.buyer_name, confidence=0.9),
                payment_terms=FieldValue(value=inv_data.payment_terms, confidence=0.9)
            )
            meta = ExtractionMeta(
                provider_name="mock",
                model_name="mock-model",
                latency_ms=100.0,
                tokens_in=100,
                tokens_out=100,
                cost_estimate=0.0
            )
            mock_provider.extract = AsyncMock(return_value=(extracted_inv, meta))
        
        # Use ExitStack-like approach or simple patch
        with patch("invoice_pipeline.stages.field_extract.get_provider", return_value=mock_provider) if use_mock_llm else patch.object(lambda: None, '__call__', return_value=None):
            async with session_factory() as session:
                doc = await run_pipeline(
                    filename=inv_data.filename,
                    file_bytes=pdf_bytes,
                    mime_type="application/pdf",
                    session=session
                )

            
            canon = doc.canonicalized
            if not canon:
                print(f"  -> Failed to canonicalize {inv_data.filename}")
                for key in metrics:
                    metrics[key].append((True, False)) # True expected, False predicted
                continue
                
            # Vendor
            vendor_match = canon.raw.vendor_name.value is not None and inv_data.vendor_name.lower() in canon.raw.vendor_name.value.lower()
            metrics["vendor"].append((True, vendor_match))
            
            # Invoice Number
            inv_num_match = canon.invoice_number == inv_data.invoice_number
            metrics["invoice_number"].append((True, inv_num_match))
            
            # Date
            date_match = canon.invoice_date == inv_data.invoice_date
            metrics["date"].append((True, date_match))
            
            # Currency
            curr_match = canon.currency == inv_data.currency
            metrics["currency"].append((True, curr_match))
            
            # Tax
            expected_tax = Decimal(str(sum(item.total for item in inv_data.line_items) * inv_data.tax_rate)).quantize(Decimal("0.01"))
            actual_tax = canon.tax_amount or Decimal("0")
            tax_match = abs(expected_tax - actual_tax) < Decimal("0.10")
            metrics["tax"].append((True, tax_match))
            
            # Line items
            expected_li = len(inv_data.line_items)
            actual_li = len(canon.raw.line_items) if canon.raw.line_items else 0
            metrics["line_items"].append((expected_li > 0, actual_li == expected_li))
            
    await engine.dispose()
    
    # Calculate scores
    final_scores = {}
    total_acc = 0
    categories = 0
    for key, pairs in metrics.items():
        trues = [p[0] for p in pairs]
        preds = [p[1] for p in pairs]
        p, r, f1, support = compute_metrics(trues, preds)
        
        # Accuracy as simple exact match rate for these fields
        acc = sum(1 for t, pred in zip(trues, preds) if t == pred and t) / sum(1 for t in trues if t) if sum(1 for t in trues if t) > 0 else 0
        
        final_scores[key] = {
            "accuracy": acc,
            "precision": p,
            "recall": r,
            "f1": f1
        }
        total_acc += acc
        categories += 1
        
    overall = total_acc / categories if categories > 0 else 0
    final_scores["overall"] = {"accuracy": overall}
    
    print(f"\nOverall Accuracy: {overall:.2%}")
    
    # Load history
    history = {}
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r") as f:
            history = json.load(f)
            
    prev_overall = history.get("overall", {}).get("accuracy", 0.0)
    diff = overall - prev_overall
    if diff < 0:
        print(f"WARNING: Regression detected! Overall accuracy dropped by {-diff:.2%}")
    elif diff > 0:
        print(f"IMPROVEMENT: Overall accuracy increased by {diff:.2%}")
        
    # Write history
    with open(HISTORY_FILE, "w") as f:
        json.dump(final_scores, f, indent=2)
        
    # Write CSV
    with open(REPORT_CSV, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Metric", "Accuracy", "Precision", "Recall", "F1 Score"])
        for k, v in final_scores.items():
            if k == "overall":
                writer.writerow(["overall", f"{v['accuracy']:.4f}", "", "", ""])
            else:
                writer.writerow([k, f"{v['accuracy']:.4f}", f"{v['precision']:.4f}", f"{v['recall']:.4f}", f"{v['f1']:.4f}"])
                
    # Write Markdown
    with open(REPORT_MD, "w") as f:
        f.write("# Extraction Benchmark Report\n\n")
        f.write(f"Generated at: {datetime.now().isoformat()}\n\n")
        
        if diff != 0:
            f.write(f"**Change from last run:** {'+' if diff > 0 else ''}{diff:.2%}\n\n")
            
        f.write("## Overall Accuracy\n")
        f.write(f"**{overall:.2%}**\n\n")
        
        f.write("## Detailed Metrics\n")
        f.write("| Field | Accuracy | Precision | Recall | F1 Score |\n")
        f.write("|---|---|---|---|---|\n")
        for k, v in final_scores.items():
            if k == "overall":
                continue
            f.write(f"| {k} | {v['accuracy']:.2%} | {v['precision']:.2f} | {v['recall']:.2f} | {v['f1']:.2f} |\n")
            
    print(f"\nReports saved to {BENCHMARK_DIR}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Extraction Benchmark")
    parser.add_argument("--mock-llm", action="store_true", help="Use a mocked LLM instead of making real API calls")
    args = parser.parse_args()
    
    asyncio.run(run_benchmark(use_mock_llm=args.mock_llm))
