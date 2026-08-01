"""Import the supplied Go interview question bank."""

import csv
import hashlib
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0024"
down_revision: str | None = "20260802_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "go_interview_questions.csv"
DATA_SHA256 = "a60f7112503d1c792ff4704ef997ce9cf5f05fd06e95b615be6040241f7bf352"
EXPECTED_FIELDS = {"Тема", "Вопрос", "Ответ с пояснением"}
EXPECTED_ROWS = 233
EXPECTED_CATEGORIES = 20

GO_TRACK_ID = UUID("40000000-0000-4000-8000-000000000002")
GO_DECK_ID = UUID("60000000-0000-4000-8000-000000000002")
GO_GOROUTINE_CARD_ID = UUID("61000000-0000-4000-8000-000000000003")
GO_INTERFACE_CARD_ID = UUID("61000000-0000-4000-8000-000000000004")
CARD_NAMESPACE = UUID("ae4212d9-bf52-4ee3-99d1-cb7b67b0635d")


def _read_rows() -> list[dict[str, str]]:
    raw_data = DATA_FILE.read_bytes()
    if hashlib.sha256(raw_data).hexdigest() != DATA_SHA256:
        raise RuntimeError("Go interview CSV checksum does not match the migration")
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or []) != EXPECTED_FIELDS:
            raise RuntimeError("Go interview CSV has unexpected columns")
        rows = list(reader)

    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(f"Expected {EXPECTED_ROWS} interview rows, got {len(rows)}")

    questions: set[str] = set()
    categories: set[str] = set()
    for row in rows:
        category = row["Тема"].strip()
        question = row["Вопрос"].strip()
        answer = row["Ответ с пояснением"].strip()
        if not category or not question or not answer:
            raise RuntimeError(
                "Every Go interview card must contain a category, question and answer"
            )
        if len(category) > 240:
            raise RuntimeError("Go interview CSV contains a category longer than 240 characters")
        normalized_question = question.casefold()
        if normalized_question in questions:
            raise RuntimeError("Go interview CSV contains duplicate questions")
        questions.add(normalized_question)
        categories.add(category)

    if len(categories) != EXPECTED_CATEGORIES:
        raise RuntimeError(
            f"Expected {EXPECTED_CATEGORIES} interview categories, got {len(categories)}"
        )
    return rows


def _card_identity(position: int, question: str) -> tuple[UUID, str]:
    source_number = position + 1
    if source_number == 69:
        return GO_GOROUTINE_CARD_ID, "go-goroutine"
    if source_number == 109:
        return GO_INTERFACE_CARD_ID, "go-interface"
    return (
        uuid5(CARD_NAMESPACE, f"go-interview:{source_number}:{question}"),
        f"go-interview-{source_number:03d}",
    )


def upgrade() -> None:
    rows = _read_rows()
    connection = op.get_bind()

    track_id = connection.scalar(sa.text("SELECT id FROM learning_tracks WHERE slug = 'go'"))
    if track_id is None:
        id_conflict = connection.scalar(
            sa.text("SELECT slug FROM learning_tracks WHERE id = :id"),
            {"id": GO_TRACK_ID},
        )
        if id_conflict is not None:
            raise RuntimeError("The reserved Go track ID is already in use")
        connection.execute(
            sa.text(
                """
                INSERT INTO learning_tracks
                    (id, slug, title, description, position, is_published)
                VALUES
                    (:id, 'go', 'Go', 'Трек Go Backend', 1, true)
                """
            ),
            {"id": GO_TRACK_ID},
        )
        track_id = GO_TRACK_ID

    deck_id = connection.scalar(
        sa.text("SELECT id FROM interview_decks WHERE slug = 'go-interview'")
    )
    if deck_id is None:
        id_conflict = connection.scalar(
            sa.text("SELECT slug FROM interview_decks WHERE id = :id"),
            {"id": GO_DECK_ID},
        )
        if id_conflict is not None:
            raise RuntimeError("The reserved Go interview deck ID is already in use")
        connection.execute(
            sa.text(
                """
                INSERT INTO interview_decks
                    (id, track_id, slug, title, description, position, is_published)
                VALUES
                    (:id, :track_id, 'go-interview',
                     'Go · вопросы с собеседований',
                     'Карточки из общей базы вопросов по Go Backend.', 0, true)
                """
            ),
            {"id": GO_DECK_ID, "track_id": track_id},
        )
        deck_id = GO_DECK_ID
    else:
        connection.execute(
            sa.text(
                """
                UPDATE interview_decks
                SET track_id = :track_id,
                    title = 'Go · вопросы с собеседований',
                    description = 'Карточки из общей базы вопросов по Go Backend.',
                    position = 0,
                    is_published = true,
                    updated_at = now()
                WHERE id = :deck_id
                """
            ),
            {"deck_id": deck_id, "track_id": track_id},
        )

    payloads: list[dict[str, object]] = []
    for position, row in enumerate(rows):
        question = row["Вопрос"].strip()
        card_id, slug = _card_identity(position, question)
        payloads.append(
            {
                "id": card_id,
                "deck_id": deck_id,
                "slug": slug,
                "category": row["Тема"].strip(),
                "source_number": position + 1,
                "question_markdown": f"## {question}",
                "answer_markdown": row["Ответ с пояснением"].strip(),
                "position": position,
            }
        )

    connection.execute(
        sa.text(
            """
            INSERT INTO interview_cards
                (id, deck_id, slug, category, companies, source_number,
                 source_occurrence, question_markdown, answer_markdown,
                 frequency, position, is_published)
            VALUES
                (:id, :deck_id, :slug, :category, NULL, :source_number,
                 NULL, :question_markdown, :answer_markdown,
                 CAST('occasional' AS interview_card_frequency), :position, true)
            ON CONFLICT (slug) DO UPDATE SET
                deck_id = EXCLUDED.deck_id,
                category = EXCLUDED.category,
                companies = NULL,
                source_number = EXCLUDED.source_number,
                source_occurrence = NULL,
                question_markdown = EXCLUDED.question_markdown,
                answer_markdown = EXCLUDED.answer_markdown,
                frequency = EXCLUDED.frequency,
                position = EXCLUDED.position,
                is_published = true,
                updated_at = now()
            """
        ),
        payloads,
    )


def downgrade() -> None:
    rows = _read_rows()
    slugs = [
        _card_identity(position, row["Вопрос"].strip())[1]
        for position, row in enumerate(rows)
        if position + 1 not in {69, 109}
    ]
    connection = op.get_bind()
    connection.execute(
        sa.text("DELETE FROM interview_cards WHERE slug IN :slugs").bindparams(
            sa.bindparam("slugs", expanding=True)
        ),
        {"slugs": slugs},
    )
    connection.execute(
        sa.text(
            """
            UPDATE interview_cards SET
                category = 'Основы Go',
                companies = NULL,
                source_number = NULL,
                source_occurrence = NULL,
                question_markdown = CASE slug
                    WHEN 'go-goroutine' THEN
                        '## Чем goroutine отличается от системного потока?'
                    ELSE '## Как тип реализует interface в Go?'
                END,
                answer_markdown = CASE slug
                    WHEN 'go-goroutine' THEN
                        'Goroutine — лёгкая конкурентная задача, которой управляет runtime '
                        'Go. Планировщик мультиплексирует множество goroutine на меньшее '
                        'число системных потоков, а их стек начинается небольшим и растёт '
                        'по мере нужды.'
                    ELSE
                        'Неявно: тип реализует interface, если его method set содержит все '
                        'методы интерфейса. Отдельное объявление `implements` не требуется, '
                        'что позволяет определять небольшие интерфейсы на стороне потребителя.'
                END,
                frequency = CASE slug
                    WHEN 'go-goroutine' THEN
                        CAST('frequent' AS interview_card_frequency)
                    ELSE CAST('occasional' AS interview_card_frequency)
                END,
                position = CASE slug WHEN 'go-goroutine' THEN 0 ELSE 1 END,
                is_published = true,
                updated_at = now()
            WHERE slug IN ('go-goroutine', 'go-interface')
            """
        )
    )
    connection.execute(
        sa.text(
            """
            DELETE FROM interview_decks AS deck
            WHERE deck.id = :deck_id
              AND deck.slug = 'go-interview'
              AND NOT EXISTS (
                  SELECT 1 FROM interview_cards AS card WHERE card.deck_id = deck.id
              )
            """
        ),
        {"deck_id": GO_DECK_ID},
    )
