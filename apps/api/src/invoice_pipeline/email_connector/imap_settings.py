"""
Provider-specific IMAP presets for Gmail, Outlook, and generic IMAP.
These are convenience defaults — users may override any value.
"""

IMAP_PROVIDERS: dict[str, dict[str, object]] = {
    "gmail": {
        "host": "imap.gmail.com",
        "port": 993,
        "use_ssl": True,
        "note": "Requires an App Password or OAuth2 token. Enable IMAP in Gmail settings.",
    },
    "outlook": {
        "host": "outlook.office365.com",
        "port": 993,
        "use_ssl": True,
        "note": "Use an App Password or OAuth2 token with modern auth.",
    },
    "imap": {
        "host": "",  # user-provided
        "port": 993,
        "use_ssl": True,
        "note": "Generic IMAP server — set host in your .env or settings.",
    },
}
