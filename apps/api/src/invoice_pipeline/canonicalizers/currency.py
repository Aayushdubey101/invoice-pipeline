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
    if not value:
        return None
    try:
        cleaned = value.strip()
        for sym in _SYMBOL_MAP:
            cleaned = cleaned.replace(sym, "")
        cleaned = cleaned.replace(",", "").strip()
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


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
