"""Shared SQL definitions for automatic work and the human review queue."""

from sqlalchemy import and_, exists, or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.interviews.card_automation_models import (
    AutomationDecision,
    CardAutomationSettings,
    QuestionCluster,
)
from app.interviews.card_automation_types import (
    AnswerContractStatus,
    AutomationDecisionSource,
    QuestionClusterStatus,
)


def ai_processing_condition() -> ColumnElement[bool]:
    enabled = exists(
        select(CardAutomationSettings.direction_id).where(
            CardAutomationSettings.direction_id == QuestionCluster.direction_id,
            CardAutomationSettings.enabled.is_(True),
            CardAutomationSettings.cluster_moderation_enabled.is_(True),
        )
    )
    auto_publish = exists(
        select(CardAutomationSettings.direction_id).where(
            CardAutomationSettings.direction_id == QuestionCluster.direction_id,
            CardAutomationSettings.enabled.is_(True),
            CardAutomationSettings.cluster_moderation_enabled.is_(True),
            CardAutomationSettings.global_auto_publish_enabled.is_(True),
            CardAutomationSettings.shadow_mode.is_(False),
        )
    )
    human_decision = exists(
        select(AutomationDecision.id).where(
            AutomationDecision.entity_type == "cluster",
            AutomationDecision.entity_id == QuestionCluster.id,
            AutomationDecision.decision_source == AutomationDecisionSource.HUMAN,
        )
    )
    return and_(
        QuestionCluster.status == QuestionClusterStatus.NEEDS_REVIEW,
        QuestionCluster.linked_card_id.is_(None),
        ~human_decision,
        enabled,
        or_(
            QuestionCluster.answer_status.is_(None),
            and_(
                QuestionCluster.answer_status == AnswerContractStatus.GENERATED_FROM_SOURCES,
                auto_publish,
            ),
        ),
    )


def manual_review_condition() -> ColumnElement[bool]:
    return and_(
        QuestionCluster.status == QuestionClusterStatus.NEEDS_REVIEW, ~ai_processing_condition()
    )
