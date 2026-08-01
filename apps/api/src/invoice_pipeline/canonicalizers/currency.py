import re
from decimal import Decimal, InvalidOperation

_SYMBOL_MAP = {
    "$": "USD",
    "€": "EUR",
    "£": "GBP",
    "¥": "JPY",
    "₹": "INR",
    "₩": "KRW",
    "₺": "TRY",
    "₽": "RUB",
    "R$": "BRL",
    "A$": "AUD",
    "C$": "CAD",
    "HK$": "HKD",
    "S$": "SGD",
}


def parse_amount(value: str | None) -> Decimal | None:
    """Parse a monetary string to Decimal, handling US and EU number formats.

    Handles: "1234.56", "$1,234.56", "1.234,56", "75 974,00", "82 003,30"
    (space/NBSP/thin-space thousands separators, comma or dot decimal).
    """
    if not value:
        return None
    # keep only digits and separators (drop currency symbols, letters, spaces)
    s = re.sub(r"[^\d.,-]", "", value.strip())
    if not s or s in {"-", ".", ","}:
        return None

    has_comma, has_dot = "," in s, "." in s
    if has_comma and has_dot:
        # rightmost separator is the decimal point; the other groups thousands
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif has_comma:
        s = _resolve_single_sep(s, ",")
    elif has_dot:
        s = _resolve_single_sep(s, ".")

    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _resolve_single_sep(s: str, sep: str) -> str:
    """One separator kind present: decide decimal vs thousands.

    Multiple occurrences → thousands. Single occurrence with exactly 3
    trailing digits → thousands (e.g. "1,234"); otherwise decimal.
    """
    parts = s.split(sep)
    if len(parts) > 2 or len(parts[-1]) == 3 and len(parts[0]) <= 3 and parts[0].lstrip("-"):
        return s.replace(sep, "")
    return s.replace(sep, ".")


def normalize_currency(value: str | None) -> str | None:
    if not value:
        return None
    v = value.strip()
    if v in _SYMBOL_MAP:
        return _SYMBOL_MAP[v]
    upper = v.upper()
    try:
        from babel.numbers import get_currency_name

        get_currency_name(upper, locale="en")
        return upper
    except Exception:
        return upper if len(upper) == 3 else None
