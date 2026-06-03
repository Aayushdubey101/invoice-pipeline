from datetime import date


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        import dateparser
        result = dateparser.parse(
            value,
            settings={"RETURN_AS_TIMEZONE_AWARE": False, "PREFER_DAY_OF_MONTH": "first"},
        )
        return result.date() if result else None
    except Exception:
        return None
