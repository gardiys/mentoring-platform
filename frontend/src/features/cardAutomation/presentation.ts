import type {
  AnswerContractStatus,
  AutomationDecisionSource,
  AutomationDecisionType,
  AutomationReviewResult,
  LearningObjectType,
  PairwiseCardMatchDecision,
  PersonalReviewStatus,
  QuestionClusterStatus,
} from "../../types/api";

export const learningObjectLabels: Record<LearningObjectType, string> = {
  flashcard: "Карточка",
  open_technical_question: "Открытый технический вопрос",
  coding_task: "Задача с кодом",
  system_design_case: "System design",
  behavioral_question: "Поведенческий вопрос",
  organizational_question: "Организационный вопрос",
  context_dependent: "Зависит от контекста",
  noise: "Шум",
};

export const clusterStatusLabels: Record<QuestionClusterStatus, string> = {
  shadow: "Теневой",
  candidate: "Кандидат",
  needs_review: "Нужна проверка",
  linked: "Связан",
  card_created: "Карточка создана",
  deferred: "Отложен",
  ignored: "Исключён",
  split: "Разделён",
  merged: "Объединён",
};

export const clusterStatusColors: Record<QuestionClusterStatus, string> = {
  shadow: "gray",
  candidate: "blue",
  needs_review: "yellow",
  linked: "green",
  card_created: "green",
  deferred: "orange",
  ignored: "gray",
  split: "violet",
  merged: "violet",
};

export const answerStatusLabels: Record<AnswerContractStatus, string> = {
  generated_from_sources: "Сформирован по источникам",
  needs_expert_source: "Нужен экспертный источник",
  needs_manual_review: "Нужна ручная проверка",
  approved: "Проверен",
  rejected: "Отклонён",
};

export const decisionTypeLabels: Record<AutomationDecisionType, string> = {
  question_routed: "Вопрос классифицирован",
  routed_as_noise: "Отнесён к шуму",
  routed_as_non_flashcard: "Не подходит для карточки",
  exact_card_match: "Точное совпадение",
  alias_card_match: "Совпадение с алиасом",
  semantic_card_match: "Смысловое совпадение",
  cluster_match: "Присоединён к кластеру",
  shadow_cluster_created: "Создан теневой кластер",
  cluster_promoted: "Кластер поднят в очередь",
  personal_review_created: "Создан личный вопрос",
  personal_review_reviewed: "Личный вопрос повторён",
  personal_review_archived: "Личный вопрос архивирован",
  answer_contract_generated: "Сформирован контракт ответа",
  answer_contract_validated: "Контракт ответа проверен",
  answer_contract_needs_source: "Для ответа нужен источник",
  answer_contract_failed: "Не удалось сформировать контракт ответа",
  answer_validation_failed: "Не удалось проверить контракт ответа",
  manual_override: "Ручная отмена",
  cluster_linked: "Кластер связан",
  card_created: "Карточка создана",
  cluster_split: "Кластер разделён",
  cluster_merged: "Кластеры объединены",
  cluster_ignored: "Кластер исключён",
  cluster_deferred: "Кластер отложен",
  cluster_reopened: "Кластер возвращён",
  cluster_marked_important: "Кластер отмечен важным",
  occurrence_failed: "Ошибка автоматической обработки",
  occurrence_reprocessed: "Появление обработано повторно",
};

export const decisionTypeColors: Record<AutomationDecisionType, string> = {
  question_routed: "blue",
  routed_as_noise: "gray",
  routed_as_non_flashcard: "gray",
  exact_card_match: "green",
  alias_card_match: "green",
  semantic_card_match: "teal",
  cluster_match: "blue",
  shadow_cluster_created: "gray",
  cluster_promoted: "violet",
  personal_review_created: "cyan",
  personal_review_reviewed: "cyan",
  personal_review_archived: "gray",
  answer_contract_generated: "blue",
  answer_contract_validated: "green",
  answer_contract_needs_source: "yellow",
  answer_contract_failed: "red",
  answer_validation_failed: "red",
  manual_override: "orange",
  cluster_linked: "green",
  card_created: "green",
  cluster_split: "violet",
  cluster_merged: "violet",
  cluster_ignored: "gray",
  cluster_deferred: "orange",
  cluster_reopened: "blue",
  cluster_marked_important: "red",
  occurrence_failed: "red",
  occurrence_reprocessed: "blue",
};

export const decisionSourceLabels: Record<AutomationDecisionSource, string> = {
  rule: "Правило",
  ai_routing: "AI-классификация",
  exact: "Точное сравнение",
  confirmed_alias: "Подтверждённый алиас",
  semantic_judge: "Semantic + AI judge",
  clustering: "Кластеризация",
  human: "Человек",
  backfill: "Backfill",
};

export const reviewResultLabels: Record<AutomationReviewResult, string> = {
  correct: "Верно",
  merge_error: "Ошибка объединения",
  classification_error: "Ошибка классификации",
  wrong_object_type: "Неверный тип вопроса",
  wrong_topic: "Неверная тема",
  other: "Другое",
};

export const judgeDecisionLabels: Record<PairwiseCardMatchDecision, string> = {
  same_card: "Та же карточка",
  related_different_scope: "Связано, но другой объём",
  not_related: "Не связано",
  uncertain: "Неоднозначно",
};

export const personalReviewStatusLabels: Record<PersonalReviewStatus, string> =
  {
    active: "Активен",
    mastered: "Освоен",
    archived: "В архиве",
    replaced_by_canonical_card: "Заменён общей карточкой",
  };

export function percent(value: number | null | undefined) {
  return value === null || value === undefined
    ? "—"
    : `${Math.round(value * 100)}%`;
}
