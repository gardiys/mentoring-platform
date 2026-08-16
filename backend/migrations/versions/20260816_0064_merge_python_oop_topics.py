"""Merge duplicate Python OOP card topics.

Revision ID: 20260816_0064
Revises: 20260816_0063
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260816_0064"
down_revision: str | None = "20260816_0063"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SOURCE_TOPIC = "ООП"
_TARGET_TOPIC = "Python ООП"


def upgrade() -> None:
    # Preserve every student's selection without violating the composite
    # primary key when both topic spellings were selected before the merge.
    op.execute(
        f"""
        INSERT INTO interview_topic_selections (user_id, deck_id, category, created_at)
        SELECT selection.user_id,
               selection.deck_id,
               '{_TARGET_TOPIC}',
               selection.created_at
          FROM interview_topic_selections AS selection
          JOIN interview_decks AS deck ON deck.id = selection.deck_id
          JOIN learning_tracks AS track ON track.id = deck.track_id
         WHERE track.slug = 'python'
           AND btrim(selection.category) = '{_SOURCE_TOPIC}'
        ON CONFLICT (user_id, deck_id, category) DO NOTHING
        """
    )
    op.execute(
        f"""
        DELETE FROM interview_topic_selections AS selection
         USING interview_decks AS deck, learning_tracks AS track
         WHERE deck.id = selection.deck_id
           AND track.id = deck.track_id
           AND track.slug = 'python'
           AND btrim(selection.category) = '{_SOURCE_TOPIC}'
        """
    )
    op.execute(
        f"""
        UPDATE interview_cards AS card
           SET category = '{_TARGET_TOPIC}'
          FROM interview_decks AS deck, learning_tracks AS track
         WHERE deck.id = card.deck_id
           AND track.id = deck.track_id
           AND track.slug = 'python'
           AND btrim(card.category) = '{_SOURCE_TOPIC}'
        """
    )
    op.execute(
        f"""
        UPDATE question_clusters AS cluster
           SET topic_name = CASE
                   WHEN btrim(cluster.topic_name) = '{_SOURCE_TOPIC}'
                   THEN '{_TARGET_TOPIC}'
                   ELSE cluster.topic_name
               END,
               topic_candidates = ARRAY(
                   SELECT mapped.label
                     FROM (
                         SELECT CASE
                                    WHEN btrim(candidate.label) = '{_SOURCE_TOPIC}'
                                    THEN '{_TARGET_TOPIC}'
                                    ELSE candidate.label
                                END AS label,
                                candidate.position
                           FROM unnest(cluster.topic_candidates)
                                WITH ORDINALITY AS candidate(label, position)
                     ) AS mapped
                    GROUP BY mapped.label
                    ORDER BY min(mapped.position)
               )
          FROM learning_tracks AS track
         WHERE track.id = cluster.direction_id
           AND track.slug = 'python'
           AND (
               btrim(cluster.topic_name) = '{_SOURCE_TOPIC}'
               OR EXISTS (
                   SELECT 1
                     FROM unnest(cluster.topic_candidates) AS candidate(label)
                    WHERE btrim(candidate.label) = '{_SOURCE_TOPIC}'
               )
           )
        """
    )
    op.execute(
        f"""
        UPDATE intelligence_questions AS question
           SET category = CASE
                   WHEN btrim(question.category) = '{_SOURCE_TOPIC}'
                   THEN '{_TARGET_TOPIC}'
                   ELSE question.category
               END,
               topic_candidates = ARRAY(
                   SELECT mapped.label
                     FROM (
                         SELECT CASE
                                    WHEN btrim(candidate.label) = '{_SOURCE_TOPIC}'
                                    THEN '{_TARGET_TOPIC}'
                                    ELSE candidate.label
                                END AS label,
                                candidate.position
                           FROM unnest(question.topic_candidates)
                                WITH ORDINALITY AS candidate(label, position)
                     ) AS mapped
                    GROUP BY mapped.label
                    ORDER BY min(mapped.position)
               )
          FROM learning_tracks AS track
         WHERE track.id = question.direction_id
           AND track.slug = 'python'
           AND (
               btrim(question.category) = '{_SOURCE_TOPIC}'
               OR EXISTS (
                   SELECT 1
                     FROM unnest(question.topic_candidates) AS candidate(label)
                    WHERE btrim(candidate.label) = '{_SOURCE_TOPIC}'
               )
           )
        """
    )


def downgrade() -> None:
    # This consolidation is intentionally irreversible: after the merge there
    # is no reliable way to distinguish records originally named "ООП" from
    # records that were already named "Python ООП".
    pass
