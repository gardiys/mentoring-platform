from __future__ import annotations

import calendar
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).parent / "documents"
PRODUCTS = {
    "repeat_python_mentorship": {
        "slug": "repeat-python-mentorship",
        "title": "Повторное менторство по Python-разработке",
    },
    "python_to_go_transition": {
        "slug": "python-to-go-transition",
        "title": "Переход из Python-разработки в Go-разработку",
    },
}


def financial_terms() -> dict[str, Any]:
    amount = 3_000_000
    return {
        "upfront_amount_minor": amount,
        "upfront_price_kopecks": amount,
        "currency": "RUB",
        "success_fee_percent": 100,
        "success_fee_is_additional": True,
        "success_fee_installments": 2,
        "success_fee_due_month_offsets": [1, 2],
        "minimum_success_fee_minor": None,
    }


def canonical_hash(snapshot: dict[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            snapshot, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def checkboxes(title: str, publication_date: str) -> dict[str, str]:
    return {
        "offer": (
            "Я ознакомился и полностью принимаю Публичную оферту на оказание "
            "информационно-консультационных услуг по программе "
            f"«{title}» в редакции от {publication_date}."
        ),
        "financial": (
            "Я понимаю, что сейчас оплачиваю 30 000 рублей, а при наступлении "
            "предусмотренного Офертой Трудоустройства дополнительно возникает "
            "результативный компонент в размере 100% расчетной суммы ежемесячн"
            "ого вознаграждения, оплачиваемый двумя равными платежами. Первона"
            "чальные 30 000 рублей не уменьшают результативный компонент."
        ),
        "truthful": (
            "Я подтверждаю полноту и достоверность предоставленных сведений о "
            "текущей работе, полученных офферах, процессах отбора и обязательс"
            "твах по предыдущим договорам."
        ),
    }


def manifest() -> list[dict[str, Any]]:
    return json.loads((ROOT / "manifest.json").read_text())  # type: ignore[no-any-return]


def validate_files(pdf: bytes, markdown: str | None = None) -> None:
    from io import BytesIO

    from pypdf import PdfReader

    if not pdf.startswith(b"%PDF-") or len(pdf) > 10_000_000:
        raise ValueError("Expected a PDF smaller than 10 MB")
    reader = PdfReader(BytesIO(pdf))
    if reader.is_encrypted or not reader.pages:
        raise ValueError("Expected a readable unencrypted PDF")
    if markdown is not None:
        pdf_text = "\n".join(page.extract_text() for page in reader.pages)
        pdf_text = re.sub(r"Редакция от \d{2}\.\d{2}\.\d{4}\s+Страница \d+", "", pdf_text)

        def normalize(value: str) -> str:
            return re.sub(r"[^\w]+", "", value).lower()

        if normalize(pdf_text) != normalize(markdown):
            raise ValueError(
                "Markdown differs from canonical PDF; import PDF only or supply matching Markdown"
            )


def calendar_due(value: date, months: int) -> date:
    year, zero_based_month = divmod(value.year * 12 + value.month - 1 + months, 12)
    month = zero_based_month + 1
    return date(year, month, min(value.day, calendar.monthrange(year, month)[1]))
