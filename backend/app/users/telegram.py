import re

TELEGRAM_USERNAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")


def normalize_telegram_username(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lstrip("@").strip()
    if not normalized:
        return None
    if not TELEGRAM_USERNAME_PATTERN.fullmatch(normalized):
        raise ValueError(
            "Enter a valid Telegram username: 5-32 Latin letters, digits or underscores, "
            "starting with a letter"
        )
    return normalized
