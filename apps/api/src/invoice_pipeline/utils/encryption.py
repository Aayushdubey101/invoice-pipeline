import os
from cryptography.fernet import Fernet

# For a real production app, ENCRYPTION_KEY must be a 32-byte url-safe base64-encoded key.
# We provide a safe default for development/testing so it works out of the box.
_DEFAULT_KEY = b"b-X1Y2Z3A4B5C6D7E8F9G0H1I2J3K4L5M6N7O8P9Q0R="

def _get_fernet() -> Fernet:
    key_str = os.environ.get("ENCRYPTION_KEY")
    key = key_str.encode() if key_str else _DEFAULT_KEY
    return Fernet(key)

def encrypt(data: str) -> str:
    """Encrypt a string and return a base64 encoded token string."""
    f = _get_fernet()
    return f.encrypt(data.encode()).decode()

def decrypt(token: str) -> str:
    """Decrypt a token string back to the original string."""
    f = _get_fernet()
    return f.decrypt(token.encode()).decode()
