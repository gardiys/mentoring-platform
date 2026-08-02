"""Add Interview Intelligence domain tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260802_0026"
down_revision: str | None = "20260802_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


ENUMS = {
    "intelligence_interview_type": (
        "hr",
        "screening",
        "technical",
        "final",
        "system_design",
        "live_coding",
        "other",
    ),
    "intelligence_processing_status": (
        "draft",
        "uploaded",
        "transcription_submitted",
        "transcribing",
        "transcript_ready",
        "awaiting_candidate_speaker",
        "analyzing",
        "ready",
        "failed",
    ),
    "intelligence_speaker_role": ("unknown", "candidate", "interviewer", "recruiter", "other"),
    "intelligence_difficulty": ("unknown", "junior", "middle", "senior"),
    "intelligence_review_source": ("ai", "mentor"),
    "intelligence_review_status": ("suggested", "approved", "edited", "rejected"),
    "intelligence_assessment": (
        "correct",
        "mostly_correct",
        "partial",
        "mostly_incorrect",
        "incorrect",
        "unable_to_assess",
    ),
    "intelligence_attempt_stage": (
        "normalize",
        "transcription_submit",
        "transcription_poll",
        "transcription_parse",
        "ai_extract",
        "ai_review",
    ),
    "intelligence_attempt_status": ("started", "completed", "failed"),
}


def _enum(name: str) -> postgresql.ENUM:
    return postgresql.ENUM(*ENUMS[name], name=name, create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    for name, values in ENUMS.items():
        postgresql.ENUM(*values, name=name).create(bind, checkfirst=True)

    op.create_table(
        "intelligence_interviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("stage_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("position_name", sa.String(240)),
        sa.Column("interview_type", _enum("intelligence_interview_type"), nullable=False),
        sa.Column(
            "processing_status",
            _enum("intelligence_processing_status"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column("duration_ms", sa.BigInteger()),
        sa.Column("normalized_audio_key", sa.String(500)),
        sa.Column("transcription_provider", sa.String(80)),
        sa.Column("transcription_provider_job_id", sa.String(500)),
        sa.Column("transcription_provider_payload", postgresql.JSONB()),
        sa.Column("candidate_speaker_id", postgresql.UUID(as_uuid=True)),
        sa.Column("failed_stage", _enum("intelligence_attempt_stage")),
        sa.Column("processing_error_code", sa.String(100)),
        sa.Column("processing_error_message", sa.Text()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["stage_id"], ["interview_process_stages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("stage_id", name="uq_intelligence_interviews_stage"),
    )
    op.create_index(
        "ix_intelligence_interviews_student_status",
        "intelligence_interviews",
        ["student_id", "processing_status"],
    )

    op.create_table(
        "intelligence_speakers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_speaker_key", sa.String(160), nullable=False),
        sa.Column(
            "role", _enum("intelligence_speaker_role"), nullable=False, server_default="unknown"
        ),
        sa.Column("display_name", sa.String(160)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["intelligence_interviews.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "interview_id", "provider_speaker_key", name="uq_intelligence_speaker_provider_key"
        ),
    )
    op.create_index(
        "ix_intelligence_speakers_interview_id", "intelligence_speakers", ["interview_id"]
    )
    op.create_foreign_key(
        "fk_int_interview_candidate_speaker",
        "intelligence_interviews",
        "intelligence_speakers",
        ["candidate_speaker_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "intelligence_utterances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("speaker_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.BigInteger(), nullable=False),
        sa.Column("end_ms", sa.BigInteger(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("start_ms >= 0 AND end_ms >= start_ms", name="valid_time_range"),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["intelligence_interviews.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["speaker_id"], ["intelligence_speakers.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "interview_id", "sequence_number", name="uq_intelligence_utterance_sequence"
        ),
    )
    op.create_index(
        "ix_intelligence_utterances_interview_start",
        "intelligence_utterances",
        ["interview_id", "start_ms"],
    )

    op.create_table(
        "intelligence_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_start_ms", sa.BigInteger(), nullable=False),
        sa.Column("question_end_ms", sa.BigInteger()),
        sa.Column("answer_start_ms", sa.BigInteger()),
        sa.Column("answer_end_ms", sa.BigInteger()),
        sa.Column(
            "question_utterance_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
        ),
        sa.Column(
            "answer_utterance_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False
        ),
        sa.Column("category", sa.String(120), nullable=False),
        sa.Column("subcategory", sa.String(160)),
        sa.Column("difficulty", _enum("intelligence_difficulty"), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="confidence_range"),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["intelligence_interviews.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "interview_id", "sequence_number", name="uq_intelligence_question_sequence"
        ),
    )
    op.create_index(
        "ix_intelligence_questions_interview_start",
        "intelligence_questions",
        ["interview_id", "question_start_ms"],
    )

    op.create_table(
        "intelligence_answers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("start_ms", sa.BigInteger()),
        sa.Column("end_ms", sa.BigInteger()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["question_id"], ["intelligence_questions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("question_id", name="uq_intelligence_answer_question"),
    )

    op.create_table(
        "intelligence_answer_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("answer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_review_id", postgresql.UUID(as_uuid=True)),
        sa.Column("source", _enum("intelligence_review_source"), nullable=False),
        sa.Column("status", _enum("intelligence_review_status"), nullable=False),
        sa.Column("assessment", _enum("intelligence_assessment"), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("summary", sa.Text()),
        sa.Column("strengths", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("problems", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("missing_points", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("incorrect_statements", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("suggested_better_answer", sa.Text()),
        sa.Column("model_name", sa.String(160)),
        sa.Column("prompt_version", sa.String(100)),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("rejection_reason", sa.String(100)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["answer_id"], ["intelligence_answers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["parent_review_id"], ["intelligence_answer_reviews.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_intelligence_reviews_answer_created",
        "intelligence_answer_reviews",
        ["answer_id", "created_at"],
    )

    op.create_table(
        "intelligence_mentor_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mentor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True)),
        sa.Column("timestamp_ms", sa.BigInteger()),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["mentor_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["student_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["intelligence_interviews.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["question_id"], ["intelligence_questions.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_intelligence_comments_interview_created",
        "intelligence_mentor_comments",
        ["interview_id", "created_at"],
    )

    op.create_table(
        "intelligence_processing_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stage", _enum("intelligence_attempt_stage"), nullable=False),
        sa.Column("status", _enum("intelligence_attempt_status"), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(80)),
        sa.Column("external_request_id", sa.String(500)),
        sa.Column("error_code", sa.String(100)),
        sa.Column("error_message", sa.Text()),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["intelligence_interviews.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "interview_id", "stage", "attempt_number", name="uq_intelligence_attempt_number"
        ),
    )
    op.create_index(
        "ix_intelligence_attempts_interview_started",
        "intelligence_processing_attempts",
        ["interview_id", "started_at"],
    )

    op.create_table(
        "intelligence_ai_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True)),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("model", sa.String(160), nullable=False),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("provider_request_id", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["intelligence_interviews.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["question_id"], ["intelligence_questions.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_intelligence_ai_usage_interview_id", "intelligence_ai_usage", ["interview_id"]
    )

    op.create_table(
        "intelligence_transcription_usage",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(80), nullable=False),
        sa.Column("duration_ms", sa.BigInteger()),
        sa.Column("provider_job_id", sa.String(500), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["interview_id"], ["intelligence_interviews.id"], ondelete="CASCADE"
        ),
    )
    op.create_index(
        "ix_intelligence_transcription_usage_interview_id",
        "intelligence_transcription_usage",
        ["interview_id"],
    )


def downgrade() -> None:
    op.drop_table("intelligence_transcription_usage")
    op.drop_table("intelligence_ai_usage")
    op.drop_table("intelligence_processing_attempts")
    op.drop_table("intelligence_mentor_comments")
    op.drop_table("intelligence_answer_reviews")
    op.drop_table("intelligence_answers")
    op.drop_table("intelligence_questions")
    op.drop_table("intelligence_utterances")
    op.drop_constraint(
        "fk_int_interview_candidate_speaker",
        "intelligence_interviews",
        type_="foreignkey",
    )
    op.drop_table("intelligence_speakers")
    op.drop_table("intelligence_interviews")
    bind = op.get_bind()
    for name, values in reversed(list(ENUMS.items())):
        postgresql.ENUM(*values, name=name).drop(bind, checkfirst=True)
