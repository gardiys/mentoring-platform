"""Add the Go roadmap schedule and verify the Python schedule."""

import csv
import hashlib
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "20260802_0025"
down_revision: str | None = "20260802_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "roadmap_theme_schedule.csv"
PYTHON_DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "python_roadmap_schedule.csv"
DATA_SHA256 = "d6b5fb2dfcc36f9fd640389a3d7f2d7240c0787a9770104501fa3a10dafb4794"
EXPECTED_FIELDS = {
    "id",
    "created_at",
    "updated_at",
    "main_theme",
    "theme",
    "weight",
    "ordering",
    "description",
    "specialization",
}
EXPECTED_PYTHON_ROWS = 18
EXPECTED_GO_ROWS = 19
EXPECTED_PYTHON_TOTAL_DAYS = 138
EXPECTED_GO_TOTAL_DAYS = 124
EXPECTED_GO_ORDERING = [*range(1, 13), *range(14, 19), 20, 21]

GO_SECTION_NAMESPACE = UUID("4e9d0790-c34b-46a2-b99e-4429b5e30dac")
GO_TOPIC_NAMESPACE = UUID("79940dbf-d85e-4aae-8a9b-04888b1d2500")
GO_CAREER_NAMESPACE = UUID("b59bb2e5-429d-4354-bc82-c04aa432032a")

# Schedule ordering -> (original Go roadmap position, original imported title).
GO_SECTION_TARGETS = {
    1: (0, "Подготовка инженера"),
    2: (1, "Go core"),
    3: (8, "Тестирование"),
    4: (2, "Алгоритмы и структуры данных"),
    5: (3, "Go Concurrency"),
    6: (4, "Go Runtime & Perfomance"),
    7: (5, "Go tooling"),
    8: (7, "HTTP/API Слой"),
    9: (9, "Интеграции и внешние API"),
    10: (10, "PostgreSQL и SQL"),
    11: (11, "Cashe (Redis и паттерны)"),
    12: (12, "Messaging/Brokers"),
    14: (13, "Observability & SRE-мышление"),
    15: (14, "Security"),
    16: (15, "Архитектура и System Design"),
    17: (16, "DevOps минимум"),
    18: (19, "Финальный “боевой” проект"),
    20: (21, "Составление легенды"),
}


def _python_row_identity(row: dict[str, str]) -> tuple[object, ...]:
    return (
        int(row["id"]),
        row["main_theme"].strip(),
        row["theme"].strip(),
        int(row["weight"]),
        int(row["ordering"]),
        row["description"].strip(),
    )


def _legacy_python_row_identity(row: dict[str, str]) -> tuple[object, ...]:
    return (
        int(row["ID"]),
        row["Раздел"].strip(),
        row["Тема"].strip(),
        int(row["Вес"]),
        int(row["Сортировка"]),
        row["Описание"].strip(),
    )


def _read_rows() -> list[dict[str, str]]:
    raw_data = DATA_FILE.read_bytes()
    if hashlib.sha256(raw_data).hexdigest() != DATA_SHA256:
        raise RuntimeError("Roadmap schedule checksum does not match the migration")
    with DATA_FILE.open(encoding="utf-8-sig", newline="") as source:
        reader = csv.DictReader(source)
        if set(reader.fieldnames or []) != EXPECTED_FIELDS:
            raise RuntimeError("Roadmap schedule has unexpected columns")
        rows = list(reader)

    if len(rows) != EXPECTED_PYTHON_ROWS + EXPECTED_GO_ROWS:
        raise RuntimeError("Roadmap schedule has an unexpected number of rows")
    if {row["specialization"].strip() for row in rows} != {"Python", "Go"}:
        raise RuntimeError("Roadmap schedule contains an unknown specialization")
    if any(
        not row["theme"].strip() or int(row["weight"]) <= 0 or int(row["ordering"]) <= 0
        for row in rows
    ):
        raise RuntimeError("Every roadmap stage must have a title and positive weight")

    python_rows = sorted(
        (row for row in rows if row["specialization"].strip() == "Python"),
        key=lambda row: int(row["ordering"]),
    )
    go_rows = sorted(
        (row for row in rows if row["specialization"].strip() == "Go"),
        key=lambda row: int(row["ordering"]),
    )
    if len(python_rows) != EXPECTED_PYTHON_ROWS:
        raise RuntimeError("Python roadmap schedule has an unexpected number of rows")
    if len(go_rows) != EXPECTED_GO_ROWS:
        raise RuntimeError("Go roadmap schedule has an unexpected number of rows")
    if sum(int(row["weight"]) for row in python_rows) != EXPECTED_PYTHON_TOTAL_DAYS:
        raise RuntimeError("Python roadmap schedule has an unexpected total duration")
    if sum(int(row["weight"]) for row in go_rows) != EXPECTED_GO_TOTAL_DAYS:
        raise RuntimeError("Go roadmap schedule has an unexpected total duration")
    if [int(row["ordering"]) for row in go_rows] != EXPECTED_GO_ORDERING:
        raise RuntimeError("Go roadmap schedule has unexpected ordering")

    with PYTHON_DATA_FILE.open(encoding="utf-8-sig", newline="") as source:
        existing_python_rows = list(csv.DictReader(source))
    if [_python_row_identity(row) for row in python_rows] != [
        _legacy_python_row_identity(row) for row in existing_python_rows
    ]:
        raise RuntimeError("Python roadmap weights do not match the existing schedule")
    return go_rows


def _section_id(position: int, title: str) -> UUID:
    return uuid5(GO_SECTION_NAMESPACE, f"go-roadmap:{position}:{title}")


def _resume_topic_id() -> UUID:
    identity = "go-roadmap:21:0:Составление легенды:without-link:True"
    return uuid5(GO_TOPIC_NAMESPACE, identity)


def _career_id(kind: str) -> UUID:
    return uuid5(GO_CAREER_NAMESPACE, kind)


def upgrade() -> None:
    rows = _read_rows()
    connection = op.get_bind()
    roadmap_id = connection.scalar(sa.text("SELECT id FROM roadmaps WHERE slug = 'go-backend'"))
    if roadmap_id is None:
        raise RuntimeError("The Go roadmap must exist before importing its schedule")

    rows_by_order = {int(row["ordering"]): row for row in rows}
    for ordering, (position, original_title) in GO_SECTION_TARGETS.items():
        row = rows_by_order[ordering]
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
                "id": _section_id(position, original_title),
                "roadmap_id": roadmap_id,
                "title": row["theme"].strip(),
                "duration_days": int(row["weight"]),
            },
        )
        if updated_id is None:
            raise RuntimeError(f"Go roadmap section for schedule row {ordering} was not found")

    resume_row = rows_by_order[20]
    connection.execute(
        sa.text(
            """
            UPDATE topics
            SET title = :title,
                content_markdown = :content_markdown,
                updated_at = now()
            WHERE id = :topic_id
            """
        ),
        {
            "topic_id": _resume_topic_id(),
            "title": resume_row["theme"].strip(),
            "content_markdown": (
                f"# {resume_row['theme'].strip()}\n\n{resume_row['description'].strip()}"
            ),
        },
    )

    job_row = rows_by_order[21]
    job_section_id = _career_id("section:job-search")
    description = job_row["description"].strip()
    content = f"# {job_row['theme'].strip()}\n\n"
    if description.startswith(("https://", "http://")):
        content += f"[Открыть схему этапа →]({description})"
    else:
        content += description
    connection.execute(
        sa.text(
            """
            INSERT INTO roadmap_sections
                (id, roadmap_id, title, description, position, duration_days)
            VALUES
                (:id, :roadmap_id, :title, :description, 23, :duration_days)
            ON CONFLICT (id) DO UPDATE SET
                roadmap_id = EXCLUDED.roadmap_id,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                position = EXCLUDED.position,
                duration_days = EXCLUDED.duration_days,
                updated_at = now()
            """
        ),
        {
            "id": job_section_id,
            "roadmap_id": roadmap_id,
            "title": job_row["theme"].strip(),
            "description": job_row["main_theme"].strip(),
            "duration_days": int(job_row["weight"]),
        },
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO topics
                (id, section_id, slug, title, description, content_markdown,
                 position, estimated_minutes, is_published)
            VALUES
                (:id, :section_id, 'go-roadmap-career-job-search', :title,
                 NULL, :content_markdown, 0, NULL, true)
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
        {
            "id": _career_id("topic:job-search"),
            "section_id": job_section_id,
            "title": job_row["theme"].strip(),
            "content_markdown": content,
        },
    )


def downgrade() -> None:
    _read_rows()
    connection = op.get_bind()
    roadmap_id = connection.scalar(sa.text("SELECT id FROM roadmaps WHERE slug = 'go-backend'"))
    if roadmap_id is None:
        return

    connection.execute(
        sa.text("DELETE FROM roadmap_sections WHERE id = :id"),
        {"id": _career_id("section:job-search")},
    )
    for position, original_title in GO_SECTION_TARGETS.values():
        connection.execute(
            sa.text(
                """
                UPDATE roadmap_sections
                SET title = :title,
                    duration_days = NULL,
                    updated_at = now()
                WHERE id = :id AND roadmap_id = :roadmap_id
                """
            ),
            {
                "id": _section_id(position, original_title),
                "roadmap_id": roadmap_id,
                "title": original_title,
            },
        )

    connection.execute(
        sa.text(
            """
            UPDATE topics
            SET title = 'Составление легенды',
                content_markdown = '# Составление легенды\n\nКонтрольная точка программы. '
                                   'Согласуйте выполнение этапа со своим ментором.',
                updated_at = now()
            WHERE id = :topic_id
            """
        ),
        {"topic_id": _resume_topic_id()},
    )
