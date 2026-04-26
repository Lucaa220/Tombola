from telegram.helpers import escape_markdown


def safe_escape_markdown(value) -> str:
    try:
        if value is None:
            return ""
        return escape_markdown(str(value), version=2)
    except Exception:
        try:
            return str(value)
        except Exception:
            return ""
