def validate_tax_id(value: str | None, country: str = "US") -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    try:
        import stdnum.util  # noqa: F401 — check stdnum available

        # Try EIN (US employer identification number)
        try:
            from stdnum.us import ein

            if ein.is_valid(cleaned):
                return ein.format(cleaned)
        except Exception:
            pass

        # Try EU VAT
        try:
            from stdnum.eu import vat

            if vat.is_valid(cleaned):
                return vat.compact(cleaned)
        except Exception:
            pass

        # Return cleaned if no validator matched
        return cleaned
    except ImportError:
        return cleaned
