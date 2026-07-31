"""Import the supplied Python interview question bank."""

import csv
import hashlib
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "20260731_0006"
down_revision: str | None = "20260731_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "python_interview_questions.csv"
DATA_SHA256 = "0fb369ac6885e3dea7fd589ff1b5c71fc0e2e6f2b9ea1b0c6f8665d84ba545c1"
EXPECTED_ROWS = 495
EXPECTED_FIELDS = {"№", "Тема", "Вопрос", "Ответ", "Компании", "Встречается"}
OCCURRENCE_VALUES = {"", "Часто", "Средне", "Иногда", "Редко"}

PYTHON_TRACK_ID = UUID("40000000-0000-4000-8000-000000000001")
PYTHON_DECK_ID = UUID("60000000-0000-4000-8000-000000000001")
PYTHON_GIL_CARD_ID = UUID("61000000-0000-4000-8000-000000000001")
PYTHON_EVENT_LOOP_CARD_ID = UUID("61000000-0000-4000-8000-000000000002")
CARD_NAMESPACE = UUID("6e33f7cc-2735-4b47-b333-3f95178d65b7")


def _read_rows() -> list[dict[str, str]]:
    raw_data = DATA_FILE.read_bytes()
    if hashlib.sha256(raw_data).hexdigest() != DATA_SHA256:
        raise RuntimeError("Python interview CSV checksum does not match the migration")
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or []) != EXPECTED_FIELDS:
            raise RuntimeError("Python interview CSV has unexpected columns")
        rows = list(reader)
    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(f"Expected {EXPECTED_ROWS} interview rows, got {len(rows)}")
    for row in rows:
        if not row["Вопрос"].strip() or not row["Ответ"].strip():
            raise RuntimeError("Every interview card must contain a question and an answer")
        if row["Встречается"].strip() not in OCCURRENCE_VALUES:
            raise RuntimeError("Interview CSV contains an unknown occurrence value")
    return rows


def _card_identity(position: int, source_number: int) -> tuple[UUID, str]:
    if source_number == 85:
        return PYTHON_GIL_CARD_ID, "python-gil"
    if source_number == 88:
        return PYTHON_EVENT_LOOP_CARD_ID, "python-event-loop"
    return (
        uuid5(CARD_NAMESPACE, f"python-interview:{position}:{source_number}"),
        f"python-interview-{source_number}-{position + 1}",
    )


def upgrade() -> None:
    op.add_column("interview_cards", sa.Column("category", sa.String(240), nullable=True))
    op.add_column("interview_cards", sa.Column("companies", sa.Text(), nullable=True))
    op.add_column("interview_cards", sa.Column("source_number", sa.Integer(), nullable=True))
    op.add_column("interview_cards", sa.Column("source_occurrence", sa.String(40), nullable=True))

    rows = _read_rows()
    connection = op.get_bind()
    track_id = connection.scalar(sa.text("SELECT id FROM learning_tracks WHERE slug = 'python'"))
    if track_id is None:
        connection.execute(
            sa.text(
                """
                INSERT INTO learning_tracks
                    (id, slug, title, description, position, is_published)
                VALUES
                    (:id, 'python', 'Python', 'Трек Python Backend', 0, true)
                """
            ),
            {"id": PYTHON_TRACK_ID},
        )
        track_id = PYTHON_TRACK_ID

    deck_id = connection.scalar(
        sa.text("SELECT id FROM interview_decks WHERE slug = 'python-interview'")
    )
    if deck_id is None:
        connection.execute(
            sa.text(
                """
                INSERT INTO interview_decks
                    (id, track_id, slug, title, description, position, is_published)
                VALUES
                    (:id, :track_id, 'python-interview',
                     'Python · вопросы с собеседований',
                     'Карточки из общей базы вопросов по Python Backend.', 0, true)
                """
            ),
            {"id": PYTHON_DECK_ID, "track_id": track_id},
        )
        deck_id = PYTHON_DECK_ID

    payloads = []
    for position, row in enumerate(rows):
        source_number = int(row["№"].strip())
        card_id, slug = _card_identity(position, source_number)
        occurrence = row["Встречается"].strip()
        payloads.append(
            {
                "id": card_id,
                "deck_id": deck_id,
                "slug": slug,
                "category": row["Тема"].strip() or None,
                "companies": row["Компании"].strip() or None,
                "source_number": source_number,
                "source_occurrence": occurrence or None,
                "question_markdown": f"## {row['Вопрос'].strip()}",
                "answer_markdown": row["Ответ"].strip(),
                "frequency": "frequent" if occurrence == "Часто" else "occasional",
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
                (:id, :deck_id, :slug, :category, :companies, :source_number,
                 :source_occurrence, :question_markdown, :answer_markdown,
                 CAST(:frequency AS interview_card_frequency), :position, true)
            ON CONFLICT (slug) DO UPDATE SET
                deck_id = EXCLUDED.deck_id,
                category = EXCLUDED.category,
                companies = EXCLUDED.companies,
                source_number = EXCLUDED.source_number,
                source_occurrence = EXCLUDED.source_occurrence,
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
        _card_identity(position, int(row["№"].strip()))[1]
        for position, row in enumerate(rows)
        if int(row["№"].strip()) not in {85, 88}
    ]
    connection = op.get_bind()
    delete_cards = sa.text("DELETE FROM interview_cards WHERE slug IN :slugs").bindparams(
        sa.bindparam("slugs", expanding=True)
    )
    connection.execute(delete_cards, {"slugs": slugs})
    connection.execute(
        sa.text(
            """
            UPDATE interview_cards SET
                category = NULL,
                companies = NULL,
                source_number = NULL,
                source_occurrence = NULL,
                question_markdown = CASE slug
                    WHEN 'python-gil' THEN '## Что такое GIL и на что он влияет?'
                    ELSE '## Как работает event loop в asyncio?'
                END,
                answer_markdown = CASE slug
                    WHEN 'python-gil' THEN
                        '**GIL** — блокировка интерпретатора CPython.'
                    ELSE
                        'Event loop переключает корутины в точках `await`.'
                END,
                frequency = 'frequent',
                position = CASE slug WHEN 'python-gil' THEN 0 ELSE 1 END,
                updated_at = now()
            WHERE slug IN ('python-gil', 'python-event-loop')
            """
        )
    )
    op.drop_column("interview_cards", "source_occurrence")
    op.drop_column("interview_cards", "source_number")
    op.drop_column("interview_cards", "companies")
    op.drop_column("interview_cards", "category")
