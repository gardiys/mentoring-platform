"""Enable validated automatic card publication and process the pending backlog."""

from alembic import op

revision = "20260921_0088"
down_revision = "20260921_0087"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint(
        op.f("ck_card_automation_settings_global_auto_publish_forbidden"),
        "card_automation_settings",
        type_="check",
    )
    op.execute(
        "INSERT INTO card_automation_settings (direction_id) "
        "SELECT id FROM learning_tracks WHERE is_published ON CONFLICT DO NOTHING"
    )
    op.execute("""
        UPDATE card_automation_settings SET enabled=true, shadow_mode=false,
          global_auto_publish_enabled=true, cluster_moderation_enabled=true,
          auto_link_exact_enabled=true, auto_link_alias_enabled=true,
          auto_link_semantic_enabled=true, auto_ignore_noise_enabled=true,
          version=version+1, updated_at=now()
        WHERE direction_id IN (SELECT id FROM learning_tracks WHERE is_published)
    """)
    op.execute("""
        UPDATE intelligence_questions q SET direction_id=p.track_id
        FROM intelligence_interviews i JOIN interview_process_stages s ON s.id=i.stage_id
        JOIN interview_processes p ON p.id=s.process_id
        WHERE q.interview_id=i.id AND q.direction_id IS NULL
    """)
    # Re-run unapplied shadow proposals, preserving all explicit human decisions.
    op.execute("""
        UPDATE intelligence_questions q SET automation_status='created',
          automation_revision=automation_revision+1, updated_at=now()
        WHERE moderation_status='pending' AND published_card_id IS NULL
          AND NOT alias_human_confirmed AND cluster_id IS NULL AND automation_status='routed'
          AND automation_decision_source IS DISTINCT FROM 'human'
          AND direction_id IN (SELECT direction_id FROM card_automation_settings
                               WHERE global_auto_publish_enabled)
          AND NOT EXISTS (SELECT 1 FROM automation_decisions d WHERE d.entity_type='occurrence'
                          AND d.entity_id=q.id AND d.decision_source='human')
    """)
    # Old analysis-only drafts cannot become their own evidence. Generate from sources instead.
    op.execute("""
        UPDATE question_clusters c SET answer_contract=NULL, answer_validation=NULL,
          answer_status=NULL, version=version+1, updated_at=now()
        WHERE status IN ('shadow','candidate','needs_review') AND linked_card_id IS NULL
          AND (answer_status IS NULL OR answer_status='needs_expert_source')
          AND answer_contract IS NOT NULL
          AND jsonb_array_length(COALESCE(answer_contract->'source_references','[]'::jsonb))=0
          AND direction_id IN (SELECT direction_id FROM card_automation_settings
                               WHERE global_auto_publish_enabled)
          AND NOT EXISTS (SELECT 1 FROM automation_decisions d WHERE d.entity_type='cluster'
                          AND d.entity_id=c.id AND d.decision_source='human')
    """)


def downgrade() -> None:
    # Already published cards and their audit history remain intact.
    op.execute(
        "UPDATE card_automation_settings SET global_auto_publish_enabled=false, "
        "version=version+1, updated_at=now()"
    )
    op.create_check_constraint(
        op.f("ck_card_automation_settings_global_auto_publish_forbidden"),
        "card_automation_settings",
        "global_auto_publish_enabled = false",
    )
