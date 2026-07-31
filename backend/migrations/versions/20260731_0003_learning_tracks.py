"""Add learning tracks and track access."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260731_0003"
down_revision: str | None = "20260731_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

PYTHON_TRACK_ID = "40000000-0000-4000-8000-000000000001"
GO_TRACK_ID = "40000000-0000-4000-8000-000000000002"


def upgrade() -> None:
    op.create_table(
        "learning_tracks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("slug", sa.String(160), nullable=False),
        sa.Column("title", sa.String(240), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("position >= 0", name="ck_learning_tracks_position_non_negative"),
        sa.PrimaryKeyConstraint("id", name="pk_learning_tracks"),
        sa.UniqueConstraint("slug", name="uq_learning_tracks_slug"),
    )
    op.create_table(
        "learning_track_roadmaps",
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("roadmap_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "position >= 0", name="ck_learning_track_roadmaps_position_non_negative"
        ),
        sa.ForeignKeyConstraint(
            ["roadmap_id"],
            ["roadmaps.id"],
            ondelete="CASCADE",
            name="fk_learning_track_roadmaps_roadmap_id_roadmaps",
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["learning_tracks.id"],
            ondelete="CASCADE",
            name="fk_learning_track_roadmaps_track_id_learning_tracks",
        ),
        sa.PrimaryKeyConstraint("track_id", "roadmap_id", name="pk_learning_track_roadmaps"),
    )
    op.create_table(
        "learning_track_enrollments",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("track_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "granted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["track_id"],
            ["learning_tracks.id"],
            ondelete="CASCADE",
            name="fk_learning_track_enrollments_track_id_learning_tracks",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
            name="fk_learning_track_enrollments_user_id_users",
        ),
        sa.PrimaryKeyConstraint("user_id", "track_id", name="pk_learning_track_enrollments"),
    )

    op.execute(
        sa.text(
            """
            INSERT INTO learning_tracks
                (id, slug, title, description, position, is_published)
            VALUES
                (CAST(:python_id AS UUID), 'python', 'Python', 'Трек Python Backend', 0, TRUE),
                (CAST(:go_id AS UUID), 'go', 'Go', 'Трек Go Backend', 1, TRUE)
            """
        ).bindparams(python_id=PYTHON_TRACK_ID, go_id=GO_TRACK_ID)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO learning_track_roadmaps (track_id, roadmap_id, position)
            SELECT CAST(:python_id AS UUID), id, position FROM roadmaps
            ON CONFLICT DO NOTHING
            """
        ).bindparams(python_id=PYTHON_TRACK_ID)
    )
    op.execute(
        sa.text(
            """
            INSERT INTO learning_track_enrollments (user_id, track_id)
            SELECT DISTINCT user_id, CAST(:python_id AS UUID) FROM roadmap_enrollments
            ON CONFLICT DO NOTHING
            """
        ).bindparams(python_id=PYTHON_TRACK_ID)
    )


def downgrade() -> None:
    op.drop_table("learning_track_enrollments")
    op.drop_table("learning_track_roadmaps")
    op.drop_table("learning_tracks")
