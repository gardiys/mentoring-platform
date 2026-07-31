"""Import the supplied Python Backend mentoring roadmap."""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from uuid import UUID, uuid5

import sqlalchemy as sa
from alembic import op

revision: str = "20260801_0008"
down_revision: str | None = "20260801_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "python_backend_roadmap.md"
DATA_SHA256 = "2ebac91e39dd97c5f64f4df2d97e58c9b24d23eacae819d7d4887c5b79d60a45"
EXPECTED_SECTIONS = 22
EXPECTED_LINKED_TOPICS = 253
EXPECTED_CHECKPOINTS = 2

PYTHON_ROADMAP_ID = UUID("30000000-0000-4000-8000-000000000001")
PYTHON_TRACK_ID = UUID("40000000-0000-4000-8000-000000000001")
LEGACY_ROADMAP_ID = UUID("30000000-0000-4000-8000-000000000099")
SECTION_NAMESPACE = UUID("ab27822d-2509-47ac-98ef-c582131c15f5")
TOPIC_NAMESPACE = UUID("f68c863d-e6c2-4322-82c1-5743328d37d8")

HEADING_PATTERN = re.compile(r"^##\s+(.+?)\s*$")
LINK_PATTERN = re.compile(r"^\s*-\s+\[(.+)]\((https?://.+)\)\s*$")


@dataclass
class SourceTopic:
    title: str
    url: str | None
    subgroup: str | None


@dataclass
class SourceSection:
    title: str
    topics: list[SourceTopic] = field(default_factory=list)


def _read_sections() -> list[SourceSection]:
    raw_data = DATA_FILE.read_bytes()
    if hashlib.sha256(raw_data).hexdigest() != DATA_SHA256:
        raise RuntimeError("Python roadmap checksum does not match the migration")

    sections: list[SourceSection] = []
    current_section: SourceSection | None = None
    current_subgroup: str | None = None
    linked_topics = 0

    for line_number, raw_line in enumerate(raw_data.decode("utf-8").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue

        heading = HEADING_PATTERN.fullmatch(line)
        if heading:
            current_section = SourceSection(title=heading.group(1).strip())
            sections.append(current_section)
            current_subgroup = None
            continue

        link = LINK_PATTERN.fullmatch(line)
        if link:
            if current_section is None:
                raise RuntimeError(f"Roadmap topic before the first section at line {line_number}")
            current_section.topics.append(
                SourceTopic(
                    title=link.group(1).strip(),
                    url=link.group(2).strip(),
                    subgroup=current_subgroup,
                )
            )
            linked_topics += 1
            continue

        if current_section is None:
            raise RuntimeError(f"Unexpected roadmap content at line {line_number}")
        current_subgroup = line

    empty_sections = [section for section in sections if not section.topics]
    for section in empty_sections:
        section.topics.append(SourceTopic(title=section.title, url=None, subgroup=None))

    if len(sections) != EXPECTED_SECTIONS:
        raise RuntimeError(f"Expected {EXPECTED_SECTIONS} roadmap sections, got {len(sections)}")
    if linked_topics != EXPECTED_LINKED_TOPICS:
        raise RuntimeError(
            f"Expected {EXPECTED_LINKED_TOPICS} linked roadmap topics, got {linked_topics}"
        )
    if len(empty_sections) != EXPECTED_CHECKPOINTS:
        raise RuntimeError(
            f"Expected {EXPECTED_CHECKPOINTS} roadmap checkpoints, got {len(empty_sections)}"
        )
    return sections


def _section_id(position: int, title: str) -> UUID:
    return uuid5(SECTION_NAMESPACE, f"python-roadmap:{position}:{title}")


def _topic_id(section_position: int, topic_position: int, topic: SourceTopic) -> UUID:
    identity = (
        f"python-roadmap:{section_position}:{topic_position}:"
        f"{topic.title}:{topic.url or 'checkpoint'}"
    )
    return uuid5(
        TOPIC_NAMESPACE,
        identity,
    )


def _archive_existing_content(connection: sa.Connection, roadmap_id: UUID) -> bool:
    imported_section_ids = [
        _section_id(position, section.title) for position, section in enumerate(_read_sections())
    ]
    legacy_section_ids = list(
        connection.scalars(
            sa.text(
                """
                SELECT id
                FROM roadmap_sections
                WHERE roadmap_id = :roadmap_id AND id NOT IN :imported_section_ids
                """
            ).bindparams(sa.bindparam("imported_section_ids", expanding=True)),
            {"roadmap_id": roadmap_id, "imported_section_ids": imported_section_ids},
        )
    )
    if not legacy_section_ids:
        return False

    archive_by_id = connection.scalar(
        sa.text("SELECT slug FROM roadmaps WHERE id = :id"), {"id": LEGACY_ROADMAP_ID}
    )
    archive_by_slug = connection.scalar(
        sa.text("SELECT id FROM roadmaps WHERE slug = 'python-backend-before-import'")
    )
    if archive_by_id not in {None, "python-backend-before-import"}:
        raise RuntimeError("The reserved legacy Python roadmap ID is already in use")
    if archive_by_slug not in {None, LEGACY_ROADMAP_ID}:
        raise RuntimeError("The reserved legacy Python roadmap slug is already in use")

    connection.execute(
        sa.text(
            """
            INSERT INTO roadmaps
                (id, slug, title, description, position, is_published)
            VALUES
                (:id, 'python-backend-before-import',
                 'Python Backend Developer · архив',
                 'Содержимое, сохранённое перед импортом полного Python-роадмапа.',
                 99, false)
            ON CONFLICT (id) DO NOTHING
            """
        ),
        {"id": LEGACY_ROADMAP_ID},
    )
    connection.execute(
        sa.text(
            """
            UPDATE roadmap_sections
            SET roadmap_id = :archive_id, updated_at = now()
            WHERE id IN :section_ids
            """
        ).bindparams(sa.bindparam("section_ids", expanding=True)),
        {"archive_id": LEGACY_ROADMAP_ID, "section_ids": legacy_section_ids},
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO roadmap_enrollments
                (user_id, roadmap_id, started_at, completed_at)
            SELECT user_id, :archive_id, started_at, completed_at
            FROM roadmap_enrollments
            WHERE roadmap_id = :roadmap_id
            ON CONFLICT DO NOTHING
            """
        ),
        {"archive_id": LEGACY_ROADMAP_ID, "roadmap_id": roadmap_id},
    )
    return True


def upgrade() -> None:
    sections = _read_sections()
    connection = op.get_bind()

    roadmap_id = connection.scalar(sa.text("SELECT id FROM roadmaps WHERE slug = 'python-backend'"))
    if roadmap_id is None:
        id_conflict = connection.scalar(
            sa.text("SELECT slug FROM roadmaps WHERE id = :id"), {"id": PYTHON_ROADMAP_ID}
        )
        if id_conflict is not None:
            raise RuntimeError("The reserved Python roadmap ID is already in use")
        connection.execute(
            sa.text(
                """
                INSERT INTO roadmaps
                    (id, slug, title, description, position, is_published)
                VALUES
                    (:id, 'python-backend', 'Python Backend Developer',
                     'Полный маршрут менторства: от основ Python до архитектуры, '
                     'инфраструктуры и подготовки к собеседованиям.', 0, true)
                """
            ),
            {"id": PYTHON_ROADMAP_ID},
        )
        roadmap_id = PYTHON_ROADMAP_ID
    else:
        _archive_existing_content(connection, roadmap_id)
        connection.execute(
            sa.text(
                """
                UPDATE roadmaps
                SET title = 'Python Backend Developer',
                    description = 'Полный маршрут менторства: от основ Python до архитектуры, '
                                  'инфраструктуры и подготовки к собеседованиям.',
                    position = 0,
                    is_published = true,
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": roadmap_id},
        )

    section_payloads: list[dict[str, object]] = []
    topic_payloads: list[dict[str, object]] = []
    for section_position, section in enumerate(sections):
        section_id = _section_id(section_position, section.title)
        section_payloads.append(
            {
                "id": section_id,
                "roadmap_id": roadmap_id,
                "title": section.title,
                "position": section_position,
            }
        )
        for topic_position, topic in enumerate(section.topics):
            if topic.url is None:
                content = (
                    f"# {topic.title}\n\n"
                    "Контрольная точка программы. Согласуйте время мок-собеседования "
                    "со своим тимлидом или ментором."
                )
            else:
                content = f"# {topic.title}\n\n[Открыть учебный материал →]({topic.url})"
            topic_payloads.append(
                {
                    "id": _topic_id(section_position, topic_position, topic),
                    "section_id": section_id,
                    "slug": f"python-roadmap-{section_position + 1:02d}-{topic_position + 1:03d}",
                    "title": topic.title,
                    "description": (
                        f"Подраздел: {topic.subgroup}" if topic.subgroup is not None else None
                    ),
                    "content_markdown": content,
                    "position": topic_position,
                }
            )

    connection.execute(
        sa.text(
            """
            INSERT INTO roadmap_sections
                (id, roadmap_id, title, description, position)
            VALUES
                (:id, :roadmap_id, :title, NULL, :position)
            ON CONFLICT (id) DO UPDATE SET
                roadmap_id = EXCLUDED.roadmap_id,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                position = EXCLUDED.position,
                updated_at = now()
            """
        ),
        section_payloads,
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO topics
                (id, section_id, slug, title, description, content_markdown,
                 position, estimated_minutes, is_published)
            VALUES
                (:id, :section_id, :slug, :title, :description, :content_markdown,
                 :position, NULL, true)
            ON CONFLICT (id) DO UPDATE SET
                section_id = EXCLUDED.section_id,
                slug = EXCLUDED.slug,
                title = EXCLUDED.title,
                description = EXCLUDED.description,
                content_markdown = EXCLUDED.content_markdown,
                position = EXCLUDED.position,
                estimated_minutes = EXCLUDED.estimated_minutes,
                is_published = true,
                updated_at = now()
            """
        ),
        topic_payloads,
    )

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

    connection.execute(
        sa.text(
            """
            INSERT INTO learning_track_roadmaps (track_id, roadmap_id, position)
            VALUES (:track_id, :roadmap_id, 0)
            ON CONFLICT (track_id, roadmap_id) DO UPDATE SET position = 0
            """
        ),
        {"track_id": track_id, "roadmap_id": roadmap_id},
    )
    connection.execute(
        sa.text(
            """
            INSERT INTO roadmap_enrollments (user_id, roadmap_id)
            SELECT user_id, :roadmap_id
            FROM learning_track_enrollments
            WHERE track_id = :track_id
            ON CONFLICT DO NOTHING
            """
        ),
        {"track_id": track_id, "roadmap_id": roadmap_id},
    )


def downgrade() -> None:
    sections = _read_sections()
    connection = op.get_bind()
    roadmap_id = connection.scalar(sa.text("SELECT id FROM roadmaps WHERE slug = 'python-backend'"))
    if roadmap_id is None:
        return

    imported_section_ids = [
        _section_id(position, section.title) for position, section in enumerate(sections)
    ]
    connection.execute(
        sa.text("DELETE FROM roadmap_sections WHERE id IN :section_ids").bindparams(
            sa.bindparam("section_ids", expanding=True)
        ),
        {"section_ids": imported_section_ids},
    )

    archive_exists = connection.scalar(
        sa.text("SELECT 1 FROM roadmaps WHERE id = :id"), {"id": LEGACY_ROADMAP_ID}
    )
    if archive_exists:
        connection.execute(
            sa.text(
                """
                UPDATE roadmap_sections
                SET roadmap_id = :roadmap_id, updated_at = now()
                WHERE roadmap_id = :archive_id
                """
            ),
            {"roadmap_id": roadmap_id, "archive_id": LEGACY_ROADMAP_ID},
        )
        connection.execute(
            sa.text("DELETE FROM roadmaps WHERE id = :id"), {"id": LEGACY_ROADMAP_ID}
        )
        connection.execute(
            sa.text(
                """
                UPDATE roadmaps
                SET description =
                        'Практический роадмап для подготовки Python Backend разработчика.',
                    updated_at = now()
                WHERE id = :id
                """
            ),
            {"id": roadmap_id},
        )
    else:
        connection.execute(sa.text("DELETE FROM roadmaps WHERE id = :id"), {"id": roadmap_id})
