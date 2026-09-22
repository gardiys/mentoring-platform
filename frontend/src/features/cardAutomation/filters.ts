import type {
  AutomationDecisionSource,
  LearningObjectType,
  QuestionClusterFilters,
  QuestionClusterStatus,
} from "../../types/api";

export const clusterStatuses: QuestionClusterStatus[] = [
  "shadow",
  "candidate",
  "needs_review",
  "linked",
  "card_created",
  "deferred",
  "ignored",
  "split",
  "merged",
];

export const learningObjectTypes: LearningObjectType[] = [
  "flashcard",
  "open_technical_question",
  "coding_task",
  "system_design_case",
  "behavioral_question",
  "organizational_question",
  "context_dependent",
  "noise",
];

export const decisionSources: AutomationDecisionSource[] = [
  "rule",
  "ai_routing",
  "exact",
  "confirmed_alias",
  "semantic_judge",
  "clustering",
  "human",
  "backfill",
];

export const sortOptions: Array<{
  value: QuestionClusterFilters["sortBy"];
  label: string;
}> = [
  { value: "priority_score", label: "Приоритет" },
  { value: "last_seen_at", label: "Последнее появление" },
  { value: "first_seen_at", label: "Первое появление" },
  { value: "occurrences_count", label: "Количество появлений" },
  { value: "cluster_confidence", label: "Confidence" },
];

function nullablePositiveInt(value: string | null) {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : null;
}

function nullableConfidence(value: string | null) {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 1 ? parsed : null;
}

export function filtersFromParams(
  params: URLSearchParams,
): QuestionClusterFilters {
  const status = params.get("status") as QuestionClusterStatus | null;
  const objectType = params.get(
    "learning_object_type",
  ) as LearningObjectType | null;
  const decisionSource = params.get(
    "decision_source",
  ) as AutomationDecisionSource | null;
  const sortBy = params.get("sort_by") as
    QuestionClusterFilters["sortBy"] | null;
  const seenFrom = params.get("seen_from");
  const seenTo = params.get("seen_to");

  return {
    directionId: params.get("direction_id"),
    statuses: status && clusterStatuses.includes(status) ? [status] : [],
    topicName: params.get("topic_name"),
    learningObjectTypes:
      objectType && learningObjectTypes.includes(objectType)
        ? [objectType]
        : [],
    minDistinctInterviews: nullablePositiveInt(
      params.get("min_distinct_interviews"),
    ),
    minDistinctCompanies: nullablePositiveInt(
      params.get("min_distinct_companies"),
    ),
    hasFailedAnswers: params.get("has_failed_answers") === "true" ? true : null,
    minConfidence: nullableConfidence(params.get("min_confidence")),
    maxConfidence: nullableConfidence(params.get("max_confidence")),
    hasPossibleDuplicate:
      params.get("has_possible_duplicate") === "true" ? true : null,
    decisionSource:
      decisionSource && decisionSources.includes(decisionSource)
        ? decisionSource
        : null,
    seenFrom: seenFrom ? `${seenFrom}T00:00:00.000Z` : null,
    seenTo: seenTo ? `${seenTo}T23:59:59.999Z` : null,
    needsActionOnly:
      params.get("processing_only") !== "true" &&
      params.get("waiting_only") !== "true" &&
      params.get("sources_only") !== "true" &&
      params.get("needs_action_only") !== "false",
    processingOnly: params.get("processing_only") === "true",
    waitingOnly: params.get("waiting_only") === "true",
    sourcesOnly: params.get("sources_only") === "true",
    sortBy:
      sortBy && sortOptions.some((option) => option.value === sortBy)
        ? sortBy
        : "priority_score",
    sortOrder: params.get("sort_order") === "asc" ? "asc" : "desc",
  };
}
