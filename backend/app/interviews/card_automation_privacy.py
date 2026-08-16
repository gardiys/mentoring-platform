from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

_EMAIL_RE = re.compile(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b")
_TELEGRAM_URL_RE = re.compile(r"(?i)\b(?:https?://)?(?:www\.)?t\.me/[A-Z0-9_]+\b")
_TELEGRAM_USERNAME_RE = re.compile(r"(?<![\w@])@[A-Z][A-Z0-9_]{4,}\b", re.IGNORECASE)
_FINANCIAL_RE = re.compile(
    r"(?i)\b(?:salary|compensation|зарплат(?:а|ы|е|у)?|оклад|доход)\b"
    r"\s*[:=\-]?\s*(?:[$€₽]\s*)?\d[\d\s.,]*"
    r"(?:\s*(?:руб(?:лей|ля|ль)?|usd|eur|доллар(?:ов|а)?|евро))?"
)
_CURRENCY_AMOUNT_RE = re.compile(
    r"(?i)(?<!\w)(?:[$€₽]\s*\d[\d\s.,]*|"
    r"\d[\d\s.,]*\s*(?:руб(?:лей|ля|ль)?|usd|eur|доллар(?:ов|а)?|евро))(?!\w)"
)
_LONG_NUMBER_RE = re.compile(r"(?<!\w)(?:\+?\d[\d\s().-]{8,}\d)(?!\w)")
_CYRILLIC_NAME_TOKEN = r"[А-ЯЁ][а-яё]{1,30}(?:-[А-ЯЁ][а-яё]{1,30})?"
_LATIN_NAME_TOKEN = r"[A-Z][a-z]{1,30}(?:-[A-Z][a-z]{1,30})?"
_PERSON_NAME_TOKEN = rf"(?:{_CYRILLIC_NAME_TOKEN}|{_LATIN_NAME_TOKEN})"
_ROLE_LABELED_PERSON_RE = re.compile(
    rf"(?P<label>(?i:(?<!\w)(?:"
    r"рекрутер|интервьюер|собеседник|кандидат|ментор|эксперт|автор|спикер|"
    r"recruiter|interviewer|candidate|mentor|expert|author|speaker|contact"
    r")(?:а|ом|у)?\b(?:\s+(?:по\s+имени|named))?\s*(?:[:=—-]\s*)?))"
    rf"(?P<name>{_PERSON_NAME_TOKEN}(?:\s+{_PERSON_NAME_TOKEN}){{0,2}})"
)
_NAME_FIELD_RE = re.compile(
    rf"(?P<label>(?i:(?<!\w)(?:имя|фамилия|name|surname)\b\s*[:=—-]\s*))"
    rf"(?P<name>{_PERSON_NAME_TOKEN}(?:\s+{_PERSON_NAME_TOKEN}){{0,2}})"
)
_CYRILLIC_TITLE_SEQUENCE_RE = re.compile(
    rf"(?<![\w-]){_CYRILLIC_NAME_TOKEN}(?:\s+{_CYRILLIC_NAME_TOKEN}){{1,2}}(?![\w-])"
)
_CYRILLIC_SURNAME_BEFORE_ACTION_RE = re.compile(
    rf"(?<![\w-])(?P<name>{_CYRILLIC_NAME_TOKEN})(?=\s+"
    r"(?i:спросил(?:а)?|сказал(?:а)?|ответил(?:а)?|представил(?:ся|ась)))"
)
_LIKELY_CYRILLIC_SURNAME_RE = re.compile(
    r"(?i)^[а-яё-]{2,}(?:"
    r"ов|ова|ев|ева|ёв|ёва|ин|ина|ын|ына|ский|ская|цкий|цкая|"
    r"енко|швили|дзе|ук|юк|ян|янц"
    r")$"
)


def _replace_labeled_person(match: re.Match[str]) -> str:
    return f"{match.group('label')}[PERSON_NAME]"


def _replace_likely_cyrillic_name(match: re.Match[str]) -> str:
    tokens = re.findall(r"[А-ЯЁ][а-яё-]+", match.group(0))
    if any(_LIKELY_CYRILLIC_SURNAME_RE.fullmatch(token) for token in tokens):
        return "[PERSON_NAME]"
    return match.group(0)


def _replace_surname_before_action(match: re.Match[str]) -> str:
    name = match.group("name")
    return "[PERSON_NAME]" if _LIKELY_CYRILLIC_SURNAME_RE.fullmatch(name) else name


def _redact_person_names(value: str) -> str:
    redacted = _ROLE_LABELED_PERSON_RE.sub(_replace_labeled_person, value)
    redacted = _NAME_FIELD_RE.sub(_replace_labeled_person, redacted)
    redacted = _CYRILLIC_TITLE_SEQUENCE_RE.sub(_replace_likely_cyrillic_name, redacted)
    return _CYRILLIC_SURNAME_BEFORE_ACTION_RE.sub(_replace_surname_before_action, redacted)


def redact_untrusted_text(
    value: str,
    sensitive_values: Sequence[str] = (),
) -> str:
    """Remove common high-risk identifiers before sending untrusted text to AI."""

    redacted = value
    for sensitive in sorted(
        {item.strip() for item in sensitive_values if len(item.strip()) >= 2},
        key=len,
        reverse=True,
    ):
        redacted = re.sub(
            re.escape(sensitive),
            "[PROFILE_IDENTIFIER]",
            redacted,
            flags=re.IGNORECASE,
        )
    redacted = _redact_person_names(redacted)
    redacted = _EMAIL_RE.sub("[EMAIL]", redacted)
    redacted = _TELEGRAM_URL_RE.sub("[TELEGRAM]", redacted)
    redacted = _TELEGRAM_USERNAME_RE.sub("[TELEGRAM]", redacted)
    redacted = _FINANCIAL_RE.sub("[FINANCIAL]", redacted)
    redacted = _CURRENCY_AMOUNT_RE.sub("[FINANCIAL]", redacted)
    return _LONG_NUMBER_RE.sub("[LONG_NUMBER]", redacted)


def redact_untrusted_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_untrusted_text(value)
    if isinstance(value, Mapping):
        return {str(key): redact_untrusted_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        return [redact_untrusted_value(item) for item in value]
    return value
