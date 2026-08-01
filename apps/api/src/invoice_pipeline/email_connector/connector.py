"""
Optional Email Connector — Phase 11.

DISABLED by default. Enable via: EMAIL_IMPORT_ENABLED=true in .env

When disabled, the core pipeline continues working normally.
When enabled, fetches invoice attachments from email and routes
each attachment through the existing run_pipeline() unchanged.

Supported providers  : Gmail, Outlook, Generic IMAP
Supported attachments: PDF, PNG, JPG, TIFF

Duplicate detection  : SHA-256 hash of file bytes. If a hash has
                       already been processed, the attachment is skipped.

Usage example (when enabled):

    from invoice_pipeline.email_connector.connector import EmailConnector

    conn = EmailConnector(
        host="imap.gmail.com",
        port=993,
        username="me@gmail.com",
        password="app-password",
    )
    conn.connect()
    attachments = conn.fetch_unread_attachments()
    conn.disconnect()

    for att in attachments:
        doc = await run_pipeline(
            filename=att["filename"],
            file_bytes=att["file_bytes"],
            mime_type=att["mime_type"],
            session=session,
        )
"""
from __future__ import annotations

import email
import hashlib
import imaplib
from email.message import Message
from typing import Any

import structlog

log = structlog.get_logger()

SUPPORTED_ATTACHMENT_TYPES: set[str] = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/jpg",
    "image/tiff",
    "image/x-tiff",
}


class EmailConnector:
    """
    IMAP-based connector for importing invoice attachments.
    This is an OPTIONAL module — the system operates normally without it.
    """

    def __init__(
        self,
        host: str,
        port: int,
        username: str,
        password: str,
        use_ssl: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_ssl = use_ssl
        self._conn: imaplib.IMAP4_SSL | imaplib.IMAP4 | None = None

    # ── Connection management ──────────────────────────────────────────────────

    def connect(self) -> None:
        """Establish IMAP connection and authenticate.

        Raises RuntimeError if EMAIL_IMPORT_ENABLED is not set — this module
        must have zero effect on the pipeline unless explicitly enabled.
        """
        from invoice_pipeline.config import settings

        if not settings.EMAIL_IMPORT_ENABLED:
            raise RuntimeError(
                "Email connector is disabled. Set EMAIL_IMPORT_ENABLED=true in .env to enable it."
            )

        timeout = settings.EMAIL_CONNECT_TIMEOUT_SECONDS
        if self.use_ssl:
            self._conn = imaplib.IMAP4_SSL(self.host, self.port, timeout=timeout)
        else:
            self._conn = imaplib.IMAP4(self.host, self.port, timeout=timeout)
        try:
            self._conn.login(self.username, self.password)
        except imaplib.IMAP4.error as exc:
            log.error("email_connector_auth_failed", host=self.host, username=self.username)
            self._conn = None
            raise RuntimeError(f"IMAP authentication failed for {self.username}@{self.host}") from exc
        log.info("email_connector_connected", host=self.host, username=self.username)

    def disconnect(self) -> None:
        """Close the IMAP connection gracefully."""
        if self._conn is not None:
            try:
                self._conn.logout()
            except Exception:
                pass
            self._conn = None
            log.info("email_connector_disconnected")

    # ── Attachment fetching ────────────────────────────────────────────────────

    def fetch_unread_attachments(self, mailbox: str = "INBOX") -> list[dict[str, Any]]:
        """
        Fetch invoice attachments from unread emails.

        Returns a list of dicts, each containing:
            message_id     : str   — RFC 2822 Message-ID header
            attachment_hash: str   — SHA-256 hex digest for dedup
            filename       : str   — original attachment filename
            file_bytes     : bytes — raw file content
            mime_type      : str   — MIME type of the attachment

        Duplicate detection: attachments whose hash is already in
        ``seen_hashes`` are skipped automatically.
        """
        if self._conn is None:
            raise RuntimeError(
                "Not connected. Call connect() before fetch_unread_attachments()."
            )

        self._conn.select(mailbox)
        _, msg_nums = self._conn.search(None, "UNSEEN")

        attachments: list[dict[str, Any]] = []
        seen_hashes: set[str] = set()

        for num in (msg_nums[0] or b"").split():
            _, msg_data = self._conn.fetch(num, "(RFC822)")
            if not msg_data or msg_data[0] is None:
                continue

            raw_email: bytes = msg_data[0][1]  # type: ignore[index]
            msg: Message = email.message_from_bytes(raw_email)
            message_id: str = msg.get("Message-ID", num.decode())

            for part in msg.walk():
                content_type = part.get_content_type()
                if content_type not in SUPPORTED_ATTACHMENT_TYPES:
                    continue

                file_bytes: bytes | None = part.get_payload(decode=True)
                if not file_bytes:
                    continue

                attachment_hash = hashlib.sha256(file_bytes).hexdigest()
                if attachment_hash in seen_hashes:
                    log.info(
                        "email_duplicate_skipped",
                        attachment_hash=attachment_hash,
                        message_id=message_id,
                    )
                    continue
                seen_hashes.add(attachment_hash)

                filename: str = part.get_filename() or f"attachment_{attachment_hash[:8]}"
                attachments.append(
                    {
                        "message_id": message_id,
                        "attachment_hash": attachment_hash,
                        "filename": filename,
                        "file_bytes": file_bytes,
                        "mime_type": content_type,
                    }
                )
                log.info(
                    "email_attachment_collected",
                    filename=filename,
                    mime_type=content_type,
                    message_id=message_id,
                )

        log.info("email_attachments_fetched", count=len(attachments))
        return attachments
