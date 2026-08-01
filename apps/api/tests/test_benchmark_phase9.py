import pytest
import asyncio
from unittest.mock import patch, mock_open
from scripts.benchmark import compute_metrics, safe_decimal, run_benchmark
from decimal import Decimal

def test_safe_decimal():
    assert safe_decimal(None) == Decimal("0")
    assert safe_decimal(10.5) == Decimal("10.5")
    assert safe_decimal("20.00") == Decimal("20.00")

def test_compute_metrics():
    trues = [True, True, False, False, True]
    preds = [True, False, True, False, True]
    
    p, r, f1, support = compute_metrics(trues, preds)
    
    # tp = 2, fp = 1, fn = 1
    # precision = 2 / 3 = 0.666
    # recall = 2 / 3 = 0.666
    # f1 = 0.666
    # support = 3
    
    assert abs(p - 0.666) < 0.01
    assert abs(r - 0.666) < 0.01
    assert support == 3

@pytest.mark.asyncio
async def test_run_benchmark():
    # Test that it runs through without errors
    # We patch the file writes to avoid creating files during test
    with patch("scripts.benchmark.open", mock_open()):
        with patch("scripts.benchmark.Path.exists", return_value=False):
            with patch("scripts.benchmark.Path.mkdir"):
                # We also mock _INVOICES to be just 1 invoice to make the test fast
                with patch("scripts.benchmark._INVOICES", [__import__("scripts.generate_synthetic_invoices").generate_synthetic_invoices._INVOICES[0]]):
                    await run_benchmark(use_mock_llm=True)
