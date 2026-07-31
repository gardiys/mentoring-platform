"""Add roadmap schedules, explicit starts and section deadlines."""

import csv
import hashlib
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0009"
down_revision: str | None = "20260801_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "python_roadmap_schedule.csv"
DATA_SHA256 = "41169788845a366a943bc1fe8ad8e7e47730a37f07c8c7cbe0c8a5aa49d52d4e"
EXPECTED_FIELDS = {"ID", "Раздел", "Тема", "Вес", "Сортировка", "Описание"}
EXPECTED_ROWS = 18
EXPECTED_TOTAL_DAYS = 138

PYTHON_ROADMAP_ID = UUID("30000000-0000-4000-8000-000000000001")
IMPORTED_SECTION_NAMESPACE = UUID("ab27822d-2509-47ac-98ef-c582131c15f5")
CAREER_NAMESPACE = UUID("6b3924b0-c64c-4054-8e97-da54060209da")

# CSV stage ID -> (original imported position, original imported title).
SECTION_TARGETS = {
    1: (0, "Основы Python"),
    2: (1, "Git"),
    3: (2, "AI-инструментарий"),
    4: (3, "Продвинутый Python"),
    5: (4, "Алгоритмы и структуры данных"),
    6: (6, "База данных"),
    7: (7, "Тестирование"),
    8: (8, "Инфраструктура"),
    9: (10, "Backend Фреймворки"),
    10: (11, "Подготовка к проектам"),
    11: (13, "Django Пет-проект"),
    12: (14, "Архитектура кода"),
    13: (15, "Архитектура приложений"),
    14: (18, "FastAPI Пет-проект"),
    15: (19, "Основы ML"),
    16: (20, "Юридические знания"),
}


def _read_rows() -> list[dict[str, str]]:
    raw_data = DATA_FILE.read_bytes()
    if hashlib.sha256(raw_data).hexdigest() != DATA_SHA256:
        raise RuntimeError("Python roadmap schedule checksum does not match the migration")
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or []) != EXPECTED_FIELDS:
            raise RuntimeError("Python roadmap schedule has unexpected columns")
        rows = list(reader)

    if len(rows) != EXPECTED_ROWS:
        raise RuntimeError(f"Expected {EXPECTED_ROWS} schedule rows, got {len(rows)}")
    if [int(row["Сортировка"]) for row in rows] != list(range(1, EXPECTED_ROWS + 1)):
        raise RuntimeError("Python roadmap schedule positions must be consecutive")
    if sum(int(row["Вес"]) for row in rows) != EXPECTED_TOTAL_DAYS:
        raise RuntimeError("Python roadmap schedule has an unexpected total duration")
    if any(int(row["Вес"]) <= 0 or not row["Тема"].strip() for row in rows):
        raise RuntimeError("Every roadmap stage must have a title and positive duration")
    return rows


def _imported_section_id(position: int, title: str) -> UUID:
    return uuid5(IMPORTED_SECTION_NAMESPACE, f"python-roadmap:{position}:{title}")


def _career_id(kind: str) -> UUID:
    return uuid5(CAREER_NAMESPACE, kind)


def upgrade() -> None:
    op.add_column(
        "roadmap_sections",
        sa.Column("duration_days", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_roadmap_sections_duration_days_positive",
        "roadmap_sections",
        "duration_days IS NULL OR duration_days > 0",
    )
    op.alter_column(
        "roadmap_enrollments",
        "started_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
        server_default=None,
    )

    # Before this migration enrollment creation and study start were the same event.
    # Keep a real start only when the learner has interacted with at least one topic.
    op.execute(
        """
        UPDATE roadmap_enrollments AS enrollment
        SET started_at = (
            SELECT min(COALESCE(
                progress.started_at,
                progress.first_completed_at,
                progress.last_completed_at
            ))
            FROM topic_progress AS progress
            JOIN topics AS topic ON topic.id = progress.topic_id
            JOIN roadmap_sections AS section ON section.id = topic.section_id
            WHERE progress.user_id = enrollment.user_id
              AND section.roadmap_id = enrollment.roadmap_id
        )
        """
    )

    rows = _read_rows()
    connection = op.get_bind()
    roadmap_id = connection.scalar(sa.text("SELECT id FROM roadmaps WHERE slug = 'python-backend'"))
    if roadmap_id is None:
        raise RuntimeError("The Python roadmap must exist before importing its schedule")

    rows_by_id = {int(row["ID"]): row for row in rows}
    for source_id, (position, original_title) in SECTION_TARGETS.items():
        section_id = _imported_section_id(position, original_title)
        row = rows_by_id[source_id]
        updated_id = connection.scalar(
            sa.text(
                """
                UPDATE roadmap_sections
                SET title = :title,
                    duration_days = :duration_days,
                    updated_at = now()
                WHERE id = :id AND roadmap_id = :roadmap_id
                RETURNING id
                """
            ),
            {
                "id": section_id,
                "roadmap_id": roadmap_id,
                "title": row["Тема"].strip(),
                "duration_days": int(row["Вес"]),
            },
        )
        if updated_id is None:
            raise RuntimeError(f"Roadmap section for schedule row {source_id} was not found")

    # Keep interview preparation between the new resume and job-search stages.
    interview_section_id = _imported_section_id(21, "Подготовка к собеседованиям")
    connection.execute(
        sa.text(
            """
            UPDATE roadmap_sections
            SET position = 22, updated_at = now()
            WHERE id = :id AND roadmap_id = :roadmap_id
            """
        ),
        {"id": interview_section_id, "roadmap_id": roadmap_id},
    )

    career_sections = []
    career_topics = []
    for source_id, position, key in ((17, 21, "resume"), (18, 23, "job-search")):
        row = rows_by_id[source_id]
        section_id = _career_id(f"section:{key}")
        topic_id = _career_id(f"topic:{key}")
        description = row["Описание"].strip()
        content = f"# {row['Тема'].strip()}\n\n"
        if description.startswith(("https://", "http://")):
            content += f"[Открыть схему этапа →]({description})"
        else:
            content += description
        career_sections.append(
            {
                "id": section_id,
                "roadmap_id": roadmap_id,
                "title": row["Тема"].strip(),
                "description": row["Раздел"].strip(),
                "position": position,
                "duration_days": int(row["Вес"]),
            }
        )
        career_topics.append(
            {
                "id": topic_id,
                "section_id": section_id,
                "slug": f"python-roadmap-career-{key}",
                "title": row["Тема"].strip(),
                "content_markdown": content,
            }
        )

    connection.execute(
        sa.text(
            """
            INSERT INTO roadmap_sections
                (id, roadmap_id, title, description, position, duration_days)
            VALUES
                (:id, :roadmap_id, :title, :description, :position, :duration_days)
            ON CONFLICT (id) DO UPDATE SET
                roadmap_id = EXCLUDED.roadmap_id,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                position = EXCLUDED.position,
                duration_days = EXCLUDED.duration_days,
                updated_at = now()
            """
        ),
        career_sections,
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO topics
                (id, section_id, slug, title, description, content_markdown,
                 position, estimated_minutes, is_published)
            VALUES
                (:id, :section_id, :slug, :title, NULL, :content_markdown,
                 0, NULL, true)
            ON CONFLICT (id) DO UPDATE SET
                section_id = EXCLUDED.section_id,
                slug = EXCLUDED.slug,
                title = EXCLUDED.title,
                content_markdown = EXCLUDED.content_markdown,
                position = 0,
                is_published = true,
                updated_at = now()
            """
        ),
        career_topics,
    )


def downgrade() -> None:
    connection = op.get_bind()
    roadmap_id = connection.scalar(sa.text("SELECT id FROM roadmaps WHERE slug = 'python-backend'"))
    if roadmap_id is not None:
        connection.execute(
            sa.text("DELETE FROM roadmap_sections WHERE id IN (:resume_id, :job_id)"),
            {
                "resume_id": _career_id("section:resume"),
                "job_id": _career_id("section:job-search"),
            },
        )
        for source_id, original_title in (
            (6, "База данных"),
            (11, "Django Пет-проект"),
            (14, "FastAPI Пет-проект"),
        ):
            position, imported_title = SECTION_TARGETS[source_id]
            connection.execute(
                sa.text(
                    """
                    UPDATE roadmap_sections
                    SET title = :title, updated_at = now()
                    WHERE id = :id AND roadmap_id = :roadmap_id
                    """
                ),
                {
                    "title": original_title,
                    "id": _imported_section_id(position, imported_title),
                    "roadmap_id": roadmap_id,
                },
            )
        connection.execute(
            sa.text(
                """
                UPDATE roadmap_sections
                SET position = 21, updated_at = now()
                WHERE id = :id AND roadmap_id = :roadmap_id
                """
            ),
            {
                "id": _imported_section_id(21, "Подготовка к собеседованиям"),
                "roadmap_id": roadmap_id,
            },
        )

    op.execute("UPDATE roadmap_enrollments SET started_at = COALESCE(started_at, now())")
    op.alter_column(
        "roadmap_enrollments",
        "started_at",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    op.drop_constraint(
        "ck_roadmap_sections_duration_days_positive",
        "roadmap_sections",
        type_="check",
    )
    op.drop_column("roadmap_sections", "duration_days")
