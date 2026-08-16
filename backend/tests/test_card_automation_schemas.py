from datetime import UTC, date, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.interviews.card_automation_schemas import (
    AnswerContract,
    AutomationDecisionOverrideMutation,
    AutomationDecisionReviewMutation,
    CardAutomationMetricsFilters,
    CardAutomationSettingsUpdate,
    PersonalReviewItemCorrectionMutation,
    QuestionClusterBulkAction,
    QuestionClusterBulkMutation,
    QuestionClusterDraftMutation,
    QuestionClusterLinkCardMutation,
    QuestionClusterListFilters,
    QuestionClusterSplitMutation,
)
from app.interviews.card_automation_types import (
    AutomationDecisionType,
    AutomationReviewResult,
)


@pytest.fixture(autouse=True)
def reset_database() -> None:
    """Override the integration-suite fixture: these are pure schema tests."""


def _settings_payload() -> dict[str, object]:
    return {
        "direction_id": uuid4(),
        "expected_version": 1,
        "enabled": False,
        "shadow_mode": True,
        "auto_ignore_noise_enabled": False,
        "auto_link_exact_enabled": False,
        "auto_link_alias_enabled": False,
        "auto_link_semantic_enabled": False,
        "semantic_similarity_threshold": 0.9,
        "pairwise_judge_confidence_threshold": 0.92,
        "candidate_score_gap_threshold": 0.08,
        "cluster_match_threshold": 0.86,
        "min_distinct_interviews_for_promotion": 3,
        "min_distinct_companies_for_promotion": 2,
        "min_failed_answers_for_promotion": 2,
        "audit_sample_percent": 5,
        "personal_review_enabled": False,
        "global_auto_publish_enabled": False,
        "cluster_moderation_enabled": False,
        "legacy_queue_enabled": True,
    }


def test_mutations_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        QuestionClusterLinkCardMutation.model_validate(
            {
                "card_id": uuid4(),
                "expected_version": 1,
                "reason": "Verified manually",
                "unexpected": True,
            }
        )


def test_split_rejects_duplicate_occurrences() -> None:
    occurrence_id = uuid4()

    with pytest.raises(ValidationError, match="occurrence_ids must be unique"):
        QuestionClusterSplitMutation(
            occurrence_ids=[occurrence_id, occurrence_id],
            new_canonical_question="What is a descriptor?",
            expected_version=1,
            reason="The scopes differ",
        )


def test_cluster_draft_requires_a_field_and_rejects_unsafe_preservation() -> None:
    with pytest.raises(ValidationError, match="at least one cluster draft field"):
        QuestionClusterDraftMutation(
            expected_version=1,
            reason="No actual draft field",
        )

    with pytest.raises(ValidationError, match="canonical_question cannot be null"):
        QuestionClusterDraftMutation(
            expected_version=1,
            reason="Invalid clear",
            canonical_question=None,
        )

    with pytest.raises(ValidationError, match="answer_contract cannot be null"):
        QuestionClusterDraftMutation(
            expected_version=1,
            reason="Invalid answer clear",
            answer_contract=None,
        )

    with pytest.raises(ValidationError, match="preserve_answer_status cannot be used"):
        QuestionClusterDraftMutation(
            expected_version=1,
            reason="Answer must be reviewed again",
            answer_contract=AnswerContract(
                short_answer="A descriptor customizes attribute access.",
                difficulty="middle",
                confidence=0.9,
            ),
            preserve_answer_status=True,
        )


def test_bulk_action_requires_exact_version_map_and_explicit_confirmation() -> None:
    first_cluster_id = uuid4()
    second_cluster_id = uuid4()

    with pytest.raises(ValidationError, match="exactly every selected cluster"):
        QuestionClusterBulkMutation(
            action=QuestionClusterBulkAction.IGNORE_NOISE,
            cluster_ids=[first_cluster_id, second_cluster_id],
            expected_versions={first_cluster_id: 1},
            confirmation=True,
            reason="Verified noise",
        )

    with pytest.raises(ValidationError, match="confirmation"):
        QuestionClusterBulkMutation.model_validate(
            {
                "action": QuestionClusterBulkAction.IGNORE_NOISE,
                "cluster_ids": [first_cluster_id],
                "expected_versions": {first_cluster_id: 1},
                "reason": "Verified noise",
            }
        )


def test_bulk_action_validates_action_specific_target() -> None:
    cluster_id = uuid4()

    with pytest.raises(ValidationError, match="card_id is required"):
        QuestionClusterBulkMutation(
            action=QuestionClusterBulkAction.LINK_CARD,
            cluster_ids=[cluster_id],
            expected_versions={cluster_id: 1},
            confirmation=True,
            reason="Same meaning",
        )


def test_settings_cannot_enable_global_auto_publish() -> None:
    payload = _settings_payload()
    payload["global_auto_publish_enabled"] = True

    with pytest.raises(ValidationError, match="global_auto_publish_enabled"):
        CardAutomationSettingsUpdate.model_validate(payload)


def test_settings_cannot_disable_every_moderation_path() -> None:
    payload = _settings_payload()
    payload.update(enabled=False, legacy_queue_enabled=False)

    with pytest.raises(ValidationError, match="legacy_queue_enabled"):
        CardAutomationSettingsUpdate.model_validate(payload)

    payload.update(enabled=True, cluster_moderation_enabled=False)
    with pytest.raises(ValidationError, match="legacy_queue_enabled"):
        CardAutomationSettingsUpdate.model_validate(payload)


def test_other_decision_review_requires_reason() -> None:
    with pytest.raises(ValidationError, match="reason is required"):
        AutomationDecisionReviewMutation(result=AutomationReviewResult.OTHER)


def test_decision_override_cannot_select_card_and_cluster() -> None:
    with pytest.raises(ValidationError, match="either a card or a cluster"):
        AutomationDecisionOverrideMutation(
            expected_entity_version=1,
            replacement_decision_type=AutomationDecisionType.MANUAL_OVERRIDE,
            selected_card_id=uuid4(),
            selected_cluster_id=uuid4(),
            reason="Corrected after review",
        )


def test_decision_override_rejects_incompatible_card_target() -> None:
    with pytest.raises(ValidationError, match="incompatible with a card target"):
        AutomationDecisionOverrideMutation(
            expected_entity_version=1,
            replacement_decision_type=AutomationDecisionType.ROUTED_AS_NOISE,
            selected_card_id=uuid4(),
            reason="This decision should not point to a card",
        )


def test_cluster_filters_reject_inverted_ranges() -> None:
    with pytest.raises(ValidationError, match="min_confidence cannot exceed"):
        QuestionClusterListFilters(min_confidence=0.8, max_confidence=0.5)

    with pytest.raises(ValidationError, match="seen_from cannot be after"):
        QuestionClusterListFilters(
            seen_from=datetime(2026, 8, 16, tzinfo=UTC),
            seen_to=datetime(2026, 8, 15, tzinfo=UTC),
        )


def test_metrics_filters_reject_inverted_period() -> None:
    with pytest.raises(ValidationError, match="period_from cannot be after"):
        CardAutomationMetricsFilters(
            period_from=date(2026, 8, 16),
            period_to=date(2026, 8, 15),
        )


def test_personal_review_correction_requires_a_real_change() -> None:
    with pytest.raises(ValidationError, match="at least one personal review field"):
        PersonalReviewItemCorrectionMutation(
            expected_version=1,
            reason="No actual correction",
        )

    with pytest.raises(ValidationError, match="question_text cannot be null"):
        PersonalReviewItemCorrectionMutation(
            expected_version=1,
            reason="Invalid clear",
            question_text=None,
        )
