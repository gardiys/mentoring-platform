"""Add the mentor workspace and import mentor-to-student assignments."""

from __future__ import annotations

import csv
import hashlib
from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260801_0021"
down_revision: str | None = "20260801_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ASSOCIATION_FILE = DATA_DIR / "mentorship_associations.csv"
USER_FILE = DATA_DIR / "legacy_users.csv"
ASSOCIATION_HASH = "8d6dc6ced374fa9418bdf6b05ce6e8ac1d0150952818182201e80cd99bd1ddd1"
ASSOCIATION_COUNT = 170


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as source:
        return list(csv.DictReader(source))


def _import_assignments(connection: sa.Connection) -> None:
    # Legacy PII exports are intentionally absent from deployment images.
    if not ASSOCIATION_FILE.is_file() or not USER_FILE.is_file():
        return
    raw = ASSOCIATION_FILE.read_bytes()
    if hashlib.sha256(raw).hexdigest() != ASSOCIATION_HASH:
        raise RuntimeError("Mentorship association checksum does not match")
    associations = _rows(ASSOCIATION_FILE)
    if len(associations) != ASSOCIATION_COUNT or set(associations[0]) != {
        "mentee_id",
        "mentor_id",
    }:
        raise RuntimeError("Mentorship association file has an unexpected structure")

    legacy_users = {row["id"]: row for row in _rows(USER_FILE)}
    telegram_to_user = {
        str(row["telegram_id"]): (row["id"], row["role"])
        for row in connection.execute(
            sa.text("SELECT id, telegram_id, role FROM users WHERE telegram_id IS NOT NULL")
        ).mappings()
    }
    skipped_guests = 0
    imported = 0
    for association in associations:
        mentee = legacy_users.get(association["mentee_id"])
        mentor = legacy_users.get(association["mentor_id"])
        if mentee is None or mentor is None:
            raise RuntimeError("Mentorship association references an unknown legacy user")
        if mentee["role"].strip() == "Гость":
            skipped_guests += 1
            continue
        mentee_record = telegram_to_user.get(mentee["telegram_id"].strip())
        mentor_record = telegram_to_user.get(mentor["telegram_id"].strip())
        if mentee_record is None or mentor_record is None:
            raise RuntimeError("A non-guest mentorship user was not imported")
        mentee_id, mentee_role = mentee_record
        mentor_id, mentor_role = mentor_record
        if str(mentee_role) != "student" or str(mentor_role) not in {"mentor", "admin"}:
            raise RuntimeError("Mentorship association contains incompatible platform roles")
        connection.execute(
            sa.text(
                """
                INSERT INTO mentor_students
                    (mentor_id, student_id, learning_status, assigned_at, status_updated_at)
                VALUES
                    (:mentor_id, :student_id,
                     CAST('learning' AS student_learning_status), now(), now())
                ON CONFLICT (student_id) DO UPDATE
                SET mentor_id = EXCLUDED.mentor_id
                """
            ),
            {"mentor_id": mentor_id, "student_id": mentee_id},
        )
        imported += 1
    if imported + skipped_guests != ASSOCIATION_COUNT:
        raise RuntimeError("Mentorship association import is incomplete")


def upgrade() -> None:
    learning_status = postgresql.ENUM(
        "learning",
        "interviewing",
        "probation",
        "finished",
        name="student_learning_status",
        create_type=False,
    )
    strength_level = postgresql.ENUM(
        "weak",
        "medium",
        "strong",
        name="student_strength_level",
        create_type=False,
    )
    document_kind = postgresql.ENUM(
        "resume", "legend", name="mentor_document_kind", create_type=False
    )
    mock_status = postgresql.ENUM(
        "planned", "completed", name="mock_interview_status", create_type=False
    )
    bind = op.get_bind()
    for enum in (learning_status, strength_level, document_kind, mock_status):
        enum.create(bind, checkfirst=True)

    op.execute(
        """
        DELETE FROM mentor_students AS relation
        USING (
            SELECT mentor_id, student_id,
                   row_number() OVER (
                       PARTITION BY student_id ORDER BY assigned_at, mentor_id
                   ) AS position
            FROM mentor_students
        ) AS duplicate
        WHERE relation.mentor_id = duplicate.mentor_id
          AND relation.student_id = duplicate.student_id
          AND duplicate.position > 1
        """
    )
    op.create_unique_constraint(
        "uq_mentor_students_one_mentor_per_student",
        "mentor_students",
        ["student_id"],
    )
    op.add_column(
        "mentor_students",
        sa.Column(
            "learning_status",
            learning_status,
            server_default=sa.text("'learning'"),
            nullable=False,
        ),
    )
    op.add_column(
        "mentor_students",
        sa.Column("strength_level", strength_level, nullable=True),
    )
    op.add_column(
        "mentor_students",
        sa.Column(
            "status_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "mentor_student_notes",
        sa.Column("mentor_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mentor_student_notes_student_created",
        "mentor_student_notes",
        ["student_id", "created_at"],
    )

    op.create_table(
        "mentor_student_documents",
        sa.Column("mentor_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("kind", document_kind, nullable=False),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("storage_key", sa.String(length=180), nullable=True),
        sa.Column("filename", sa.String(length=500), nullable=True),
        sa.Column("content_type", sa.String(length=160), nullable=True),
        sa.Column("size", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "text_content IS NOT NULL OR storage_key IS NOT NULL",
            name="ck_mentor_student_documents_document_has_content",
        ),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "student_id",
            "kind",
            name="uq_mentor_student_documents_one_document_per_kind",
        ),
    )

    op.create_table(
        "mock_interviews",
        sa.Column("mentor_id", sa.UUID(), nullable=False),
        sa.Column("student_id", sa.UUID(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            mock_status,
            server_default=sa.text("'planned'"),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("feedback", sa.Text(), nullable=True),
        sa.Column("conducted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("media_storage_key", sa.String(length=180), nullable=True),
        sa.Column("media_filename", sa.String(length=500), nullable=True),
        sa.Column("media_content_type", sa.String(length=160), nullable=True),
        sa.Column("media_size", sa.BigInteger(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_mock_interviews_student_scheduled",
        "mock_interviews",
        ["student_id", "scheduled_at"],
    )
    op.create_index(
        "ix_mock_interviews_mentor_scheduled",
        "mock_interviews",
        ["mentor_id", "scheduled_at"],
    )
    _import_assignments(bind)


def downgrade() -> None:
    op.drop_index("ix_mock_interviews_mentor_scheduled", table_name="mock_interviews")
    op.drop_index("ix_mock_interviews_student_scheduled", table_name="mock_interviews")
    op.drop_table("mock_interviews")
    op.drop_table("mentor_student_documents")
    op.drop_index("ix_mentor_student_notes_student_created", table_name="mentor_student_notes")
    op.drop_table("mentor_student_notes")
    op.drop_column("mentor_students", "status_updated_at")
    op.drop_column("mentor_students", "strength_level")
    op.drop_column("mentor_students", "learning_status")
    op.drop_constraint(
        "uq_mentor_students_one_mentor_per_student",
        "mentor_students",
        type_="unique",
    )
    bind = op.get_bind()
    for name in (
        "mock_interview_status",
        "mentor_document_kind",
        "student_strength_level",
        "student_learning_status",
    ):
        postgresql.ENUM(name=name).drop(bind, checkfirst=True)
