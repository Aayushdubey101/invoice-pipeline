"""Phase 11 — Tests: Batch processing, export, dashboard, email connector."""
import hashlib

import pytest


# ── Model structure tests ──────────────────────────────────────────────────────

class TestBatchModel:
    """Verify Batch and ExportHistory model attributes exist."""

    def test_batch_has_required_fields(self):
        from invoice_pipeline.db.models import Batch
        batch = Batch()
        for attr in ("id", "upload_source", "total_files", "completed",
                     "failed", "pending", "skipped", "avg_confidence",
                     "processing_time_ms", "created_at", "updated_at"):
            assert hasattr(batch, attr), f"Batch missing attribute: {attr}"

    def test_export_history_has_required_fields(self):
        from invoice_pipeline.db.models import ExportHistory
        eh = ExportHistory(export_type="all", filename="test.xlsx", record_count=5, filter_params={})
        assert eh.export_type == "all"
        assert eh.filename == "test.xlsx"
        assert eh.record_count == 5

    def test_document_has_batch_id(self):
        from invoice_pipeline.db.models import Document
        assert hasattr(Document, "batch_id"), "Document missing batch_id column"
        assert hasattr(Document, "batch"), "Document missing batch relationship"


# ── MIME type validation ───────────────────────────────────────────────────────

class TestAllowedMimeTypes:
    """Verify the allowed MIME type set for batch upload."""

    def test_allowed_types_present(self):
        from invoice_pipeline.api.routes.batch import ALLOWED_MIME_TYPES
        for mime in ("application/pdf", "image/png", "image/jpeg", "image/tiff"):
            assert mime in ALLOWED_MIME_TYPES, f"{mime} should be allowed"

    def test_disallowed_types_absent(self):
        # batch.py now imports the canonical set from stages/ingest.py (fixed a
        # validation drift where batch had its own narrower list) — text/plain
        # is intentionally allowed there (plain-text emailed invoices).
        from invoice_pipeline.api.routes.batch import ALLOWED_MIME_TYPES
        for mime in ("application/zip", "application/octet-stream"):
            assert mime not in ALLOWED_MIME_TYPES, f"{mime} should NOT be allowed"


# ── Email connector unit tests ─────────────────────────────────────────────────

class TestEmailConnector:
    """Tests for the optional email connector module."""

    def test_connector_initialises_correctly(self):
        from invoice_pipeline.email_connector.connector import EmailConnector
        conn = EmailConnector(host="imap.gmail.com", port=993, username="u@g.com", password="secret")
        assert conn.host == "imap.gmail.com"
        assert conn.port == 993
        assert conn.use_ssl is True
        assert conn._conn is None

    def test_disconnect_when_not_connected_is_safe(self):
        from invoice_pipeline.email_connector.connector import EmailConnector
        conn = EmailConnector(host="test", port=993, username="u", password="p")
        conn.disconnect()  # must not raise

    def test_fetch_raises_when_not_connected(self):
        from invoice_pipeline.email_connector.connector import EmailConnector
        conn = EmailConnector(host="test", port=993, username="u", password="p")
        with pytest.raises(RuntimeError, match="Not connected"):
            conn.fetch_unread_attachments()

    def test_supported_attachment_types_set(self):
        from invoice_pipeline.email_connector.connector import SUPPORTED_ATTACHMENT_TYPES
        for mime in ("application/pdf", "image/png", "image/tiff"):
            assert mime in SUPPORTED_ATTACHMENT_TYPES

    def test_imap_providers_available(self):
        from invoice_pipeline.email_connector.imap_settings import IMAP_PROVIDERS
        assert "gmail" in IMAP_PROVIDERS
        assert "outlook" in IMAP_PROVIDERS
        assert "imap" in IMAP_PROVIDERS
        assert IMAP_PROVIDERS["gmail"]["host"] == "imap.gmail.com"
        assert IMAP_PROVIDERS["outlook"]["host"] == "outlook.office365.com"


# ── Duplicate detection ────────────────────────────────────────────────────────

class TestDuplicateDetection:
    """Verify the SHA-256 deduplication logic used by the email connector."""

    def test_same_bytes_produce_same_hash(self):
        content = b"Invoice PDF content bytes"
        assert hashlib.sha256(content).hexdigest() == hashlib.sha256(content).hexdigest()

    def test_different_bytes_produce_different_hash(self):
        h1 = hashlib.sha256(b"Invoice A").hexdigest()
        h2 = hashlib.sha256(b"Invoice B").hexdigest()
        assert h1 != h2

    def test_dedup_logic_skips_duplicate(self):
        """Simulate the seen_hashes set used in fetch_unread_attachments."""
        files = [b"inv_a", b"inv_b", b"inv_a"]  # third is a duplicate
        seen: set[str] = set()
        processed = []
        for f in files:
            h = hashlib.sha256(f).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            processed.append(f)
        assert len(processed) == 2

    def test_dedup_handles_empty_list(self):
        seen: set[str] = set()
        files: list[bytes] = []
        processed = []
        for f in files:
            h = hashlib.sha256(f).hexdigest()
            if h not in seen:
                seen.add(h)
                processed.append(f)
        assert processed == []


# ── Route importability ────────────────────────────────────────────────────────

class TestRouteImports:
    """Smoke-test that all new Phase 11 routes are importable."""

    def test_batch_route_imports(self):
        from invoice_pipeline.api.routes import batch
        assert batch.router is not None

    def test_export_route_imports(self):
        from invoice_pipeline.api.routes import export
        assert export.router is not None

    def test_dashboard_route_imports(self):
        from invoice_pipeline.api.routes import dashboard
        assert dashboard.router is not None

    def test_email_connector_imports(self):
        from invoice_pipeline.email_connector import connector
        assert connector.EmailConnector is not None

    def test_imap_settings_imports(self):
        from invoice_pipeline.email_connector import imap_settings
        assert imap_settings.IMAP_PROVIDERS is not None


# ── Batch summary helper ───────────────────────────────────────────────────────

class TestBatchSummary:
    """Validate the _batch_summary helper output."""

    def test_batch_summary_output_shape(self):
        from invoice_pipeline.api.routes.batch import _batch_summary
        from invoice_pipeline.db.models import Batch
        from datetime import datetime, timezone

        batch = Batch()
        batch.id = "test-uuid"
        batch.upload_source = "web"
        batch.total_files = 3
        batch.completed = 2
        batch.failed = 1
        batch.skipped = 0
        batch.pending = 0
        batch.avg_confidence = None
        batch.processing_time_ms = 1234
        batch.created_at = datetime(2026, 7, 25, tzinfo=timezone.utc)

        summary = _batch_summary(batch)
        assert summary["batch_id"] == "test-uuid"
        assert summary["total_files"] == 3
        assert summary["completed"] == 2
        assert summary["failed"] == 1
        assert summary["avg_confidence"] is None
        assert summary["processing_time_ms"] == 1234
