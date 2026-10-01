"""Unattributed speech, recognition confidence and durable Soniox cleanup."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261001_0096"
down_revision = "20260930_0095"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("intelligence_utterances", "speaker_id", nullable=True)
    op.add_column(
        "intelligence_utterances",
        sa.Column("recognition_quality", postgresql.JSONB(), nullable=True),
    )
    op.create_table(
        "intelligence_transcription_cleanup",
        sa.Column("provider_job_id", sa.String(500), primary_key=True),
        sa.Column("interview_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_intelligence_transcription_cleanup_interview_id",
        "intelligence_transcription_cleanup",
        ["interview_id"],
    )
    op.create_index(
        "ix_intelligence_transcription_cleanup_next_attempt_at",
        "intelligence_transcription_cleanup",
        ["next_attempt_at"],
    )
    op.execute("""INSERT INTO intelligence_transcription_cleanup (provider_job_id, interview_id)
        SELECT transcription_provider_job_id, id FROM intelligence_interviews
        WHERE transcription_provider = 'soniox' AND transcription_provider_job_id IS NOT NULL
        UNION
        SELECT external_request_id, interview_id FROM intelligence_processing_attempts
        WHERE provider = 'soniox' AND stage = 'transcription_submit'
            AND external_request_id IS NOT NULL
        ON CONFLICT DO NOTHING""")
    # Remove synthetic Soniox speakers, preserving all source speech.
    op.execute("""UPDATE intelligence_interviews SET candidate_speaker_id = NULL,
        processing_status = 'awaiting_candidate_speaker'
        WHERE candidate_speaker_id IN (SELECT s.id FROM intelligence_speakers s
        JOIN intelligence_interviews i ON i.id = s.interview_id
        WHERE i.transcription_provider = 'soniox' AND s.provider_speaker_key = 'unknown')""")
    op.execute("""UPDATE intelligence_utterances SET speaker_id = NULL WHERE speaker_id IN (
        SELECT s.id FROM intelligence_speakers s
        JOIN intelligence_interviews i ON i.id = s.interview_id
        WHERE i.transcription_provider = 'soniox' AND s.provider_speaker_key = 'unknown')""")
    op.execute("""DELETE FROM intelligence_speakers s USING intelligence_interviews i
        WHERE s.interview_id = i.id AND i.transcription_provider = 'soniox'
        AND s.provider_speaker_key = 'unknown'""")

    op.execute("""UPDATE intelligence_interviews i
        SET transcription_provider_payload = COALESCE(transcription_provider_payload, '{}'::jsonb)
            || jsonb_build_object('quality', jsonb_build_object(
                'speaker_count', q.speaker_count,
                'unattributed_utterances', q.unknown_count,
                'unattributed_fraction', q.unknown_fraction,
                'requires_review', q.speaker_count < 2 OR q.unknown_fraction > 0.1))
        FROM (
            SELECT interview_id, COUNT(DISTINCT speaker_id) AS speaker_count,
                COUNT(*) FILTER (WHERE speaker_id IS NULL) AS unknown_count,
                COALESCE(SUM(length(text)) FILTER (WHERE speaker_id IS NULL), 0)::float
                    / GREATEST(SUM(length(text)), 1) AS unknown_fraction
            FROM intelligence_utterances GROUP BY interview_id
        ) q
        WHERE i.id = q.interview_id AND i.transcription_provider = 'soniox'
            AND NOT COALESCE(i.transcription_provider_payload, '{}'::jsonb) ? 'quality'""")


def downgrade():
    # Refuse a lossy downgrade rather than delete unattributed source speech.
    op.alter_column("intelligence_utterances", "speaker_id", nullable=False)
    op.drop_column("intelligence_utterances", "recognition_quality")
    op.drop_table("intelligence_transcription_cleanup")
