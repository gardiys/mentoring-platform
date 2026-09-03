from __future__ import annotations

import html
import io
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

FONT_CANDIDATES = (
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    Path("/Library/Fonts/Arial Unicode.ttf"),
)

SELF_PRESENTATION_LABELS = {
    "target_position": "Целевая позиция",
    "target_seniority": "Целевой уровень",
    "short_positioning": "Краткое позиционирование",
    "self_presentation_structure": "Структура самопрезентации",
    "key_experience_points": "Ключевой опыт",
    "key_projects": "Ключевые проекты",
    "achievements_to_highlight": "Достижения для акцента",
    "technologies_to_highlight": "Технологии для акцента",
    "personal_contribution_points": "Личный вклад",
    "difficult_or_risky_topics": "Сложные и рискованные темы",
    "questions_to_prepare": "Вопросы для подготовки",
    "inconsistencies_or_missing_facts": "Факты, которые нужно уточнить",
    "preparation_checklist": "Чек-лист подготовки",
    "additional_notes": "Дополнительные рекомендации",
}

SEARCH_LABELS = {
    "target_positions": "Целевые должности",
    "target_seniority": "Целевой уровень",
    "primary_technology_stack": "Основной стек",
    "secondary_technology_stack": "Дополнительный стек",
    "employment_formats": "Формат работы",
    "work_schedule_preferences": "Пожелания по графику",
    "geography": "География",
    "remote_preferences": "Удаленная работа",
    "relocation_preferences": "Релокация",
    "salary_min": "Минимальная зарплата",
    "salary_target": "Целевая зарплата",
    "salary_currency": "Валюта",
    "search_channels": "Каналы поиска",
    "applications_per_workday": "Откликов в рабочий день",
    "applications_per_week": "Откликов в неделю",
    "resume_refresh_schedule": "Обновление резюме",
    "inbound_processing_rules": "Обработка входящих сообщений",
    "interview_logging_rules": "Фиксация собеседований",
    "interview_preparation_priorities": "Приоритеты подготовки",
    "funnel_control_points": "Контрольные точки воронки",
    "resume_revision_threshold": "Когда пересматривать резюме",
    "strategy_revision_threshold": "Когда пересматривать стратегию",
    "start_date": "Дата начала поиска",
    "additional_notes": "Дополнительные рекомендации",
}


def _display_value(value: object) -> str:
    if value is None:
        return "—"
    if isinstance(value, list):
        return "<br/>".join(f"• {html.escape(str(item))}" for item in value) or "—"
    return html.escape(str(value))


def _section_html(title: str, data: Mapping[str, object], labels: Mapping[str, str]) -> str:
    rows = "".join(
        f"<section><h3>{html.escape(labels.get(key, key))}</h3>"
        f"<div>{_display_value(value)}</div></section>"
        for key, value in data.items()
    )
    return f"<h2>{html.escape(title)}</h2>{rows}"


def render_package_html(snapshot: Mapping[str, Any]) -> str:
    resume = snapshot["resume"]
    self_card = snapshot["self_presentation_card"]
    search = snapshot["active_search_parameters"]
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<title>Карьерный пакет</title></head><body>"
        f"<h1>Карьерный пакет № {html.escape(str(snapshot['package_number']))}</h1>"
        f"<p>Версия {int(snapshot['version_number'])} · "
        f"{html.escape(str(snapshot['direction']))} · "
        f"{html.escape(str(snapshot['student_name']))}</p>"
        "<h2>Финальная версия резюме</h2>"
        f"<p>Версия {int(resume['version_number'])}; SHA-256: "
        f"{html.escape(str(resume['content_sha256']))}</p>"
        + _section_html("Карта подготовки к самопрезентации", self_card, SELF_PRESENTATION_LABELS)
        + _section_html("Параметры активного поиска", search, SEARCH_LABELS)
        + "</body></html>"
    )


def _font_name() -> str:
    for candidate in FONT_CANDIDATES:
        if candidate.is_file():
            name = "CareerPackageUnicode"
            if name not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont(name, str(candidate)))
            return name
    raise RuntimeError("Unicode font for career package PDF is not installed")


def _content_lines(data: Mapping[str, object], labels: Mapping[str, str]) -> Iterable[str]:
    for key, value in data.items():
        yield f"<b>{html.escape(labels.get(key, key))}</b>"
        yield _display_value(value)


def render_package_pdf(snapshot: Mapping[str, Any], snapshot_sha256: str) -> bytes:
    font = _font_name()
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    body = ParagraphStyle(
        "CareerBody",
        parent=styles["BodyText"],
        fontName=font,
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#15283d"),
        spaceAfter=4 * mm,
    )
    heading = ParagraphStyle(
        "CareerHeading",
        parent=body,
        fontSize=15,
        leading=20,
        spaceBefore=5 * mm,
        spaceAfter=3 * mm,
        textColor=colors.HexColor("#1f8fff"),
    )
    title = ParagraphStyle(
        "CareerTitle",
        parent=heading,
        fontSize=22,
        leading=28,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#102033"),
    )

    def footer(canvas: Any, document: Any) -> None:
        canvas.saveState()
        canvas.setFont(font, 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(18 * mm, 10 * mm, f"SHA-256 snapshot: {snapshot_sha256}")
        canvas.drawRightString(192 * mm, 10 * mm, f"Страница {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title="Карьерный пакет",
        author="Mentor OS",
    )
    resume = snapshot["resume"]
    story: list[Any] = [
        Paragraph("Карьерный пакет", title),
        Paragraph(
            f"№ {html.escape(str(snapshot['package_number']))} · версия "
            f"{int(snapshot['version_number'])}",
            body,
        ),
        Paragraph(
            f"Ученик: {html.escape(str(snapshot['student_name']))}<br/>"
            f"Направление: {html.escape(str(snapshot['direction']))}<br/>"
            f"Дата формирования: {html.escape(str(snapshot['published_at']))}",
            body,
        ),
        Paragraph("1. Финальная версия резюме", heading),
        Paragraph(
            f"Версия: {int(resume['version_number'])}<br/>"
            f"Файл: {html.escape(str(resume.get('filename') or 'текстовая версия'))}<br/>"
            f"SHA-256: {html.escape(str(resume['content_sha256']))}",
            body,
        ),
        PageBreak(),
        Paragraph("2. Карта подготовки к самопрезентации", heading),
    ]
    for line in _content_lines(snapshot["self_presentation_card"], SELF_PRESENTATION_LABELS):
        story.append(Paragraph(line, body))
    story.extend([Spacer(1, 3 * mm), Paragraph("3. Параметры активного поиска", heading)])
    for line in _content_lines(snapshot["active_search_parameters"], SEARCH_LABELS):
        story.append(Paragraph(line, body))
    story.append(
        Paragraph(f"Технический идентификатор документа: {html.escape(snapshot_sha256)}", body)
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
