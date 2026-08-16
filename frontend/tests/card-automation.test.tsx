import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { ApiError } from "../src/api/client";
import { api } from "../src/api/endpoints";
import { AdminCardAutomationClusterDetailPage } from "../src/pages/AdminCardAutomationClusterDetailPage";
import { AdminCardAutomationClustersPage } from "../src/pages/AdminCardAutomationClustersPage";
import { AdminCardAutomationDecisionsPage } from "../src/pages/AdminCardAutomationDecisionsPage";
import { AdminCardAutomationMetricsPage } from "../src/pages/AdminCardAutomationMetricsPage";
import { AdminCardAutomationSettingsPage } from "../src/pages/AdminCardAutomationSettingsPage";
import { MentorCardAutomationClusterDetailPage } from "../src/pages/MentorCardAutomationClusterDetailPage";
import { MentorCardAutomationClustersPage } from "../src/pages/MentorCardAutomationClustersPage";
import { MentorCardAutomationDecisionsPage } from "../src/pages/MentorCardAutomationDecisionsPage";
import {
  AdminManagedPersonalReviewPage,
  MentorManagedPersonalReviewPage,
} from "../src/pages/ManagedPersonalReviewPage";
import { PersonalReviewPage } from "../src/pages/PersonalReviewPage";
import type {
  AutomationDecisionRead,
  CardAutomationMetricsRead,
  CardAutomationSettingsRead,
  PersonalReviewItemRead,
  QuestionClusterDetail,
  QuestionClusterSummary,
} from "../src/types/api";
import { renderPage } from "./render";

const directionId = "30000000-0000-4000-8000-000000000001";
const clusterId = "50000000-0000-4000-8000-000000000001";
const secondClusterId = "50000000-0000-4000-8000-000000000002";

const cluster: QuestionClusterSummary = {
  id: clusterId,
  direction_id: directionId,
  direction_title: "Python",
  direction_slug: "python",
  status: "needs_review",
  canonical_question: "Как работает GIL?",
  learning_object_type: "flashcard",
  deck_id: null,
  topic_name: "Python core",
  subtopic_name: null,
  topic_candidates: ["Python core"],
  linked_card_id: null,
  last_decision_source: "clustering",
  occurrences_count: 4,
  distinct_interviews_count: 3,
  distinct_companies_count: 2,
  distinct_students_count: 3,
  failed_answers_count: 2,
  priority_score: 8.4,
  quality_score: 0.92,
  cluster_confidence: 0.94,
  best_match: {
    card_id: "60000000-0000-4000-8000-000000000001",
    question_markdown: "Что такое GIL?",
    answer_markdown: "GIL допускает исполнение байткода одним потоком за раз.",
    category: "Python core",
    semantic_score: 0.95,
    combined_score: 0.96,
    judge_decision: "same_card",
    judge_confidence: 0.97,
    judge_reason: "Одинаковая проверяемая идея",
    is_confirmed_alias: false,
  },
  first_seen_at: "2026-08-01T10:00:00Z",
  last_seen_at: "2026-08-16T10:00:00Z",
  manual_important: false,
  version: 4,
  allowed_actions: [
    "link_card",
    "create_card",
    "update_draft",
    "split",
    "merge",
    "ignore",
    "defer",
    "mark_important",
    "reopen",
  ],
};

const secondCluster: QuestionClusterSummary = {
  ...cluster,
  id: secondClusterId,
  canonical_question: "Чем генератор отличается от итератора?",
  version: 7,
};

const decision: AutomationDecisionRead = {
  id: "40000000-0000-4000-8000-000000000001",
  entity_type: "question_cluster",
  entity_id: "50000000-0000-4000-8000-000000000001",
  entity_version: 3,
  question_text: "Как работает GIL?",
  decision_type: "semantic_card_match",
  decision_source: "semantic_judge",
  selected_card_id: "60000000-0000-4000-8000-000000000001",
  selected_card_question: "Что такое GIL?",
  selected_cluster_id: null,
  selected_cluster_question: null,
  candidate_card_ids: ["60000000-0000-4000-8000-000000000001"],
  candidate_cluster_ids: [],
  retrieval_scores: { semantic: 0.94 },
  judge_result: { decision: "same_card" },
  confidence: 0.96,
  similarity_score: 0.94,
  reason: "Высокоуверенное совпадение",
  model_provider: "openai",
  model_name: "gpt-test",
  prompt_version: "v3",
  schema_version: "v1",
  input_tokens: 120,
  output_tokens: 30,
  cost: "0.001",
  latency_ms: 100,
  is_audit_sample: true,
  review_result: null,
  reviewed_by_user_id: null,
  reviewed_by_name: null,
  reviewed_at: null,
  review_reason: null,
  is_overridden: false,
  overridden_by_user_id: null,
  overridden_by_name: null,
  override_reason: null,
  overridden_at: null,
  created_at: "2026-08-16T10:00:00Z",
};

const clusterDetail: QuestionClusterDetail = {
  ...cluster,
  normalized_canonical_question: "как работает gil",
  representative_occurrence_id: "51000000-0000-4000-8000-000000000001",
  merged_into_cluster_id: null,
  parent_cluster_id: null,
  question_variants: [
    {
      question_text: "Как работает GIL?",
      normalized_question_text: "как работает gil",
      occurrences_count: 4,
      first_seen_at: "2026-08-01T10:00:00Z",
      last_seen_at: "2026-08-16T10:00:00Z",
    },
  ],
  companies: [
    {
      company_id: "52000000-0000-4000-8000-000000000001",
      company_name: "Acme",
      occurrences_count: 4,
    },
  ],
  interviews: [
    {
      interview_id: "53000000-0000-4000-8000-000000000001",
      company_id: "52000000-0000-4000-8000-000000000001",
      company_name: "Acme",
      interviewed_at: "2026-08-16T09:00:00Z",
      occurrences_count: 1,
    },
  ],
  answer_contract: {
    short_answer: "GIL сериализует исполнение Python-байткода.",
    required_points: ["В один момент байткод исполняет один поток"],
    optional_points: [],
    common_mistakes: [],
    unsupported_claims: [],
    follow_up_questions: [],
    difficulty: "middle",
    version_scope: ["CPython"],
    source_references: ["internal://python/gil"],
    confidence: 0.93,
  },
  answer_validation: null,
  answer_status: "generated_from_sources",
  occurrences: [
    {
      id: "51000000-0000-4000-8000-000000000001",
      interview_id: "53000000-0000-4000-8000-000000000001",
      student_id: "54000000-0000-4000-8000-000000000001",
      student_name: "Анна",
      company_id: "52000000-0000-4000-8000-000000000001",
      company_name: "Acme",
      interviewed_at: "2026-08-16T09:00:00Z",
      question_text: "Как в CPython работает GIL?",
      canonical_question_candidate: "Как работает GIL?",
      source_context: null,
      answer_text: "Один поток выполняет байткод.",
      answer_assessment: null,
      learning_object_type: "flashcard",
      routing_confidence: 0.96,
      quality_flags: [],
      automation_status: "routed",
      automation_revision: 2,
      automation_error: null,
      created_at: "2026-08-16T09:30:00Z",
    },
  ],
  top_card_matches: cluster.best_match ? [cluster.best_match] : [],
  topic_options: [
    {
      deck_id: "60000000-0000-4000-8000-000000000010",
      deck_title: "Python Questions",
      topics: ["Python core", "Параллелизм в Python", "Runtime Python"],
    },
  ],
  decisions: [decision],
  manual_history: [],
  promoted_at: "2026-08-16T09:35:00Z",
  promotion_reason: "Повторился на трёх интервью",
  membership_revision: 4,
  stats_revision: 4,
};

const settings: CardAutomationSettingsRead = {
  direction_id: directionId,
  direction_title: "Python",
  direction_slug: "python",
  enabled: false,
  shadow_mode: true,
  auto_ignore_noise_enabled: true,
  auto_link_exact_enabled: true,
  auto_link_alias_enabled: true,
  auto_link_semantic_enabled: false,
  semantic_similarity_threshold: 0.9,
  pairwise_judge_confidence_threshold: 0.95,
  candidate_score_gap_threshold: 0.08,
  cluster_match_threshold: 0.9,
  min_distinct_interviews_for_promotion: 3,
  min_distinct_companies_for_promotion: 2,
  min_failed_answers_for_promotion: 2,
  audit_sample_percent: 5,
  personal_review_enabled: false,
  global_auto_publish_enabled: false,
  cluster_moderation_enabled: false,
  legacy_queue_enabled: true,
  version: 4,
  updated_at: "2026-08-16T10:00:00Z",
};

const metrics: CardAutomationMetricsRead = {
  period_from: "2026-08-01",
  period_to: "2026-08-16",
  direction_id: directionId,
  direction_slug: "python",
  extracted_questions_total: 120,
  routed_as_noise_total: 14,
  routed_as_non_flashcard_total: 6,
  auto_linked_exact_total: 25,
  auto_linked_alias_total: 10,
  auto_linked_semantic_total: 8,
  shadow_clusters_created_total: 40,
  clusters_promoted_total: 9,
  clusters_reviewed_total: 7,
  personal_review_items_created_total: 18,
  manual_tasks_per_100_interviews: 3.5,
  average_cluster_moderation_time: 5400,
  oldest_moderation_task_age: 172800,
  automatic_decision_override_rate: 0.025,
  false_merge_rate: 0.01,
  noise_false_positive_rate: 0.04,
  average_ai_cost_per_interview: "0.024",
  average_ai_cost_per_question: "0.0032",
  average_ai_cost_per_promoted_cluster: "0.081",
  generated_at: "2026-08-16T10:00:00Z",
};

const personalItem: PersonalReviewItemRead = {
  id: "70000000-0000-4000-8000-000000000001",
  direction_id: directionId,
  direction_title: "Python",
  direction_slug: "python",
  source_occurrence_id: "71000000-0000-4000-8000-000000000001",
  source_analysis_id: "72000000-0000-4000-8000-000000000001",
  source_analysis_url: "/interviews/analysis/analysis-1",
  canonical_card_id: null,
  replaced_by_card_id: null,
  question_text: "Почему потоки не ускоряют CPU-bound код?",
  answer_summary: "Из-за GIL байткод CPython исполняет один поток.",
  answer_contract: {
    short_answer: "GIL сериализует исполнение Python-байткода.",
    required_points: ["Один поток исполняет байткод"],
    optional_points: [],
    common_mistakes: [],
    unsupported_claims: [],
    follow_up_questions: [],
    difficulty: "middle",
    version_scope: ["CPython"],
    source_references: ["internal://python/gil"],
    confidence: 0.93,
  },
  status: "active",
  due_at: "2026-08-16T09:00:00Z",
  last_reviewed_at: null,
  successful_reviews_count: 0,
  expires_at: null,
  version: 3,
  created_at: "2026-08-15T10:00:00Z",
  updated_at: "2026-08-16T10:00:00Z",
};

afterEach(() => vi.restoreAllMocks());

it("передаёт cluster-фильтры и пагинацию в точном backend-контракте", async () => {
  vi.spyOn(api, "adminTracks").mockResolvedValue([]);
  const list = vi.spyOn(api, "adminCardAutomationClusters").mockResolvedValue({
    items: [],
    total: 0,
    limit: 20,
    offset: 20,
  });

  renderPage(
    <AdminCardAutomationClustersPage />,
    "/admin/card-automation/clusters?status=needs_review&learning_object_type=flashcard&min_distinct_interviews=3&has_possible_duplicate=true&seen_from=2026-08-01&sort_by=last_seen_at&page=2",
    "/admin/card-automation/clusters",
  );

  expect(
    await screen.findByText("Карточек на проверку нет"),
  ).toBeInTheDocument();
  expect(list).toHaveBeenCalledWith(
    expect.objectContaining({
      statuses: ["needs_review"],
      learningObjectTypes: ["flashcard"],
      minDistinctInterviews: 3,
      hasPossibleDuplicate: true,
      seenFrom: "2026-08-01T00:00:00.000Z",
      needsActionOnly: true,
      sortBy: "last_seen_at",
      sortOrder: "desc",
    }),
    { limit: 20, offset: 20 },
  );
});

it("маршрутизирует очередь ментора в scoped API без admin-контролов", async () => {
  const adminTracks = vi.spyOn(api, "adminTracks").mockResolvedValue([]);
  const adminList = vi
    .spyOn(api, "adminCardAutomationClusters")
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  const mentorList = vi
    .spyOn(api, "mentorCardAutomationClusters")
    .mockResolvedValue({ items: [cluster], total: 1, limit: 20, offset: 0 });

  renderPage(
    <MentorCardAutomationClustersPage />,
    `/mentor/card-automation/clusters?direction_id=${directionId}`,
    "/mentor/card-automation/clusters",
  );

  expect(
    await screen.findByText(cluster.canonical_question),
  ).toBeInTheDocument();
  expect(mentorList).toHaveBeenCalledWith(
    expect.objectContaining({ directionId: null }),
    { limit: 20, offset: 0 },
  );
  expect(adminList).not.toHaveBeenCalled();
  expect(adminTracks).not.toHaveBeenCalled();
  expect(screen.queryByLabelText("Направление")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Массовое действие" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("tab", { name: "Метрики" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("tab", { name: "Настройки" }),
  ).not.toBeInTheDocument();
});

it("не показывает ментору admin-действия и вызывает его state endpoint", async () => {
  const user = userEvent.setup();
  const adminDetail = vi
    .spyOn(api, "adminCardAutomationCluster")
    .mockResolvedValue(clusterDetail);
  const adminDecks = vi
    .spyOn(api, "adminInterviewDeckSummaries")
    .mockResolvedValue([]);
  vi.spyOn(api, "mentorCardAutomationCluster").mockResolvedValue(clusterDetail);
  const stateMutation = vi
    .spyOn(api, "setMentorCardAutomationClusterState")
    .mockResolvedValue({
      cluster,
      decision_id: "55000000-0000-4000-8000-000000000001",
      affected_cluster_ids: [cluster.id],
    });
  vi.spyOn(window, "prompt").mockReturnValue("важно для программы");
  vi.spyOn(window, "confirm").mockReturnValue(true);

  renderPage(
    <MentorCardAutomationClusterDetailPage />,
    `/mentor/card-automation/clusters/${cluster.id}`,
    "/mentor/card-automation/clusters/:clusterId",
  );

  await user.click(
    await screen.findByRole("button", { name: "Пометить важным" }),
  );
  await waitFor(() =>
    expect(stateMutation).toHaveBeenCalledWith(
      cluster.id,
      "mark-important",
      { expected_version: 4, reason: "важно для программы" },
      expect.any(String),
    ),
  );

  expect(
    screen.queryByRole("button", {
      name: "Связать с выбранной карточкой",
    }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("tab", { name: "Расширенная правка" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText("Создать общую карточку")).not.toBeInTheDocument();
  expect(
    screen.queryByText("Объединить с другим кластером"),
  ).not.toBeInTheDocument();
  expect(adminDetail).not.toHaveBeenCalled();
  expect(adminDecks).not.toHaveBeenCalled();
});

it("показывает ментору тему, вопрос и ответ и сохраняет его исправления", async () => {
  const user = userEvent.setup();
  const adminUpdate = vi
    .spyOn(api, "updateAdminCardAutomationClusterDraft")
    .mockResolvedValue({
      cluster,
      decision_id: decision.id,
      affected_cluster_ids: [cluster.id],
    });
  vi.spyOn(api, "mentorCardAutomationCluster").mockResolvedValue({
    ...clusterDetail,
    allowed_actions: ["update_draft", "mark_important", "defer", "ignore"],
  });
  const mentorUpdate = vi
    .spyOn(api, "updateMentorCardAutomationClusterDraft")
    .mockResolvedValue({
      cluster: { ...cluster, version: 5 },
      decision_id: decision.id,
      affected_cluster_ids: [cluster.id],
    });
  vi.spyOn(window, "prompt").mockReturnValue("Уточнил ответ после проверки");

  renderPage(
    <MentorCardAutomationClusterDetailPage />,
    `/mentor/card-automation/clusters/${cluster.id}`,
    "/mentor/card-automation/clusters/:clusterId",
  );

  const broadTopicFields = await screen.findAllByLabelText(/1\. Широкая тема/);
  expect(
    broadTopicFields.find((element) => element.tagName === "INPUT"),
  ).toHaveValue("Python core");
  expect(screen.getByLabelText("2. Формулировка вопроса")).toHaveValue(
    cluster.canonical_question,
  );
  const answer = screen.getByLabelText("3. Ответ карточки");
  await user.clear(answer);
  await user.type(answer, "Исправленный ментором ответ про GIL.");
  await user.click(
    screen.getByRole("button", { name: "Сохранить исправления" }),
  );

  await waitFor(() =>
    expect(mentorUpdate).toHaveBeenCalledWith(
      cluster.id,
      {
        answer_contract: {
          ...clusterDetail.answer_contract,
          short_answer: "Исправленный ментором ответ про GIL.",
        },
        preserve_answer_status: false,
        expected_version: cluster.version,
        reason: "Уточнил ответ после проверки",
      },
      expect.any(String),
    ),
  );
  expect(adminUpdate).not.toHaveBeenCalled();
});

it("не подставляет первую широкую тему, если AI выбрал неизвестное значение", async () => {
  vi.spyOn(api, "adminCardAutomationCluster").mockResolvedValue({
    ...clusterDetail,
    topic_name: "Выдуманная AI тема",
    topic_candidates: ["Выдуманная AI тема"],
  });
  vi.spyOn(api, "adminInterviewDeckSummaries").mockResolvedValue([]);

  renderPage(
    <AdminCardAutomationClusterDetailPage />,
    `/admin/card-automation/clusters/${cluster.id}`,
    "/admin/card-automation/clusters/:clusterId",
  );

  expect(
    await screen.findByText("AI не выбрал широкую тему"),
  ).toBeInTheDocument();
  const broadTopicFields = await screen.findAllByLabelText(/1\. Широкая тема/);
  expect(
    broadTopicFields.find((element) => element.tagName === "INPUT"),
  ).toHaveValue("");
});

it("версионированно сохраняет проверенный черновик и синхронизирует создание карточки", async () => {
  const user = userEvent.setup();
  const updatedQuestion = "Как GIL ограничивает CPU-bound потоки в CPython?";
  const updatedTopic = "Параллелизм в Python";
  const updatedAnswer =
    "GIL разрешает исполнять Python-байткод только одному потоку одновременно.";
  const updatedDetail: QuestionClusterDetail = {
    ...clusterDetail,
    canonical_question: updatedQuestion,
    normalized_canonical_question:
      "как gil ограничивает cpu bound потоки в cpython",
    topic_name: updatedTopic,
    answer_contract: {
      ...clusterDetail.answer_contract!,
      short_answer: updatedAnswer,
    },
    answer_status: "needs_manual_review",
    version: 5,
  };
  const detail = vi
    .spyOn(api, "adminCardAutomationCluster")
    .mockResolvedValueOnce(clusterDetail)
    .mockResolvedValue(updatedDetail);
  vi.spyOn(api, "adminInterviewDeckSummaries").mockResolvedValue([]);
  const update = vi
    .spyOn(api, "updateAdminCardAutomationClusterDraft")
    .mockResolvedValue({
      cluster: {
        ...cluster,
        canonical_question: updatedQuestion,
        topic_name: updatedTopic,
        version: 5,
      },
      decision_id: "55000000-0000-4000-8000-000000000002",
      affected_cluster_ids: [cluster.id],
    });

  renderPage(
    <AdminCardAutomationClusterDetailPage />,
    `/admin/card-automation/clusters/${cluster.id}`,
    "/admin/card-automation/clusters/:clusterId",
  );

  await user.click(
    await screen.findByRole("tab", { name: "Расширенная правка" }),
  );
  const canonicalQuestion = await screen.findByLabelText(/Канонический вопрос/);
  await user.clear(canonicalQuestion);
  await user.type(canonicalQuestion, updatedQuestion);
  const topic = screen.getByPlaceholderText("Выберите тему из базы карточек");
  await user.click(topic);
  await user.keyboard("{ArrowUp}{Enter}");
  const shortAnswer = screen.getByLabelText(/Краткий проверенный ответ/);
  await user.clear(shortAnswer);
  await user.type(shortAnswer, updatedAnswer);
  await user.type(
    screen.getByLabelText(/Причина изменения/),
    "Уточнил формулировку и сверил ответ с документацией",
  );
  await user.click(
    screen.getByRole("button", { name: "Сохранить проверенный черновик" }),
  );

  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      cluster.id,
      {
        canonical_question: updatedQuestion,
        topic_name: updatedTopic,
        answer_contract: {
          ...clusterDetail.answer_contract,
          short_answer: updatedAnswer,
        },
        preserve_answer_status: false,
        expected_version: 4,
        reason: "Уточнил формулировку и сверил ответ с документацией",
      },
      expect.any(String),
    ),
  );
  expect(detail.mock.calls.length).toBeGreaterThan(1);
  expect(
    await screen.findByRole("heading", { name: updatedQuestion }),
  ).toBeInTheDocument();

  await user.click(screen.getByRole("tab", { name: "Проверка карточки" }));
  expect(
    screen.getByRole("heading", { name: "Предложение AI" }),
  ).toBeInTheDocument();
  expect(screen.getByPlaceholderText("Выберите тему")).toHaveValue(
    updatedTopic,
  );
  expect(screen.getByLabelText("2. Формулировка вопроса")).toHaveValue(
    updatedQuestion,
  );
  expect(screen.getByLabelText("3. Ответ карточки")).toHaveValue(updatedAnswer);
});

it("при конфликте черновика предлагает загрузить актуальную версию", async () => {
  const user = userEvent.setup();
  const actualDetail: QuestionClusterDetail = {
    ...clusterDetail,
    canonical_question: "Актуальная формулировка другого администратора",
    normalized_canonical_question:
      "актуальная формулировка другого администратора",
    version: 5,
  };
  const detail = vi
    .spyOn(api, "adminCardAutomationCluster")
    .mockResolvedValueOnce(clusterDetail)
    .mockResolvedValue(actualDetail);
  vi.spyOn(api, "adminInterviewDeckSummaries").mockResolvedValue([]);
  vi.spyOn(api, "updateAdminCardAutomationClusterDraft").mockRejectedValue(
    new ApiError(409, "question_cluster_version_conflict", "Версия устарела"),
  );
  vi.spyOn(window, "confirm").mockReturnValue(true);

  renderPage(
    <AdminCardAutomationClusterDetailPage />,
    `/admin/card-automation/clusters/${cluster.id}`,
    "/admin/card-automation/clusters/:clusterId",
  );

  await user.click(
    await screen.findByRole("tab", { name: "Расширенная правка" }),
  );
  const canonicalQuestion = await screen.findByLabelText(/Канонический вопрос/);
  await user.clear(canonicalQuestion);
  await user.type(canonicalQuestion, "Моя устаревшая правка");
  await user.type(
    screen.getByLabelText(/Причина изменения/),
    "Проверил вручную",
  );
  await user.click(
    screen.getByRole("button", { name: "Сохранить проверенный черновик" }),
  );

  expect(
    await screen.findByText("Кластер уже изменён другим пользователем"),
  ).toBeInTheDocument();
  await user.click(
    screen.getByRole("button", { name: "Загрузить актуальную версию" }),
  );
  expect(window.confirm).toHaveBeenCalledWith(
    "Загрузить актуальную версию? Несохранённые поля формы будут сброшены.",
  );
  await waitFor(() => expect(detail.mock.calls.length).toBeGreaterThan(1));
  await user.click(
    await screen.findByRole("tab", { name: "Расширенная правка" }),
  );
  expect(screen.getByLabelText(/Канонический вопрос/)).toHaveValue(
    actualDetail.canonical_question,
  );
});

it("позволяет изменить тему кластера без AI-ответа и не отправляет пустой контракт", async () => {
  const user = userEvent.setup();
  const noAnswerDetail: QuestionClusterDetail = {
    ...clusterDetail,
    answer_contract: null,
    answer_status: null,
  };
  vi.spyOn(api, "adminCardAutomationCluster")
    .mockResolvedValueOnce(noAnswerDetail)
    .mockResolvedValue({
      ...noAnswerDetail,
      topic_name: "Runtime Python",
      version: 5,
    });
  vi.spyOn(api, "adminInterviewDeckSummaries").mockResolvedValue([]);
  const update = vi
    .spyOn(api, "updateAdminCardAutomationClusterDraft")
    .mockResolvedValue({
      cluster: { ...cluster, topic_name: "Runtime Python", version: 5 },
      decision_id: "55000000-0000-4000-8000-000000000003",
      affected_cluster_ids: [cluster.id],
    });

  renderPage(
    <AdminCardAutomationClusterDetailPage />,
    `/admin/card-automation/clusters/${cluster.id}`,
    "/admin/card-automation/clusters/:clusterId",
  );
  await user.click(
    await screen.findByRole("tab", { name: "Расширенная правка" }),
  );
  const topic = await screen.findByPlaceholderText(
    "Выберите тему из базы карточек",
  );
  await user.click(topic);
  await user.keyboard("{ArrowDown}{Enter}");
  await user.type(screen.getByLabelText(/Причина изменения/), "Уточнил тему");
  await user.click(
    screen.getByRole("button", { name: "Сохранить проверенный черновик" }),
  );

  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      cluster.id,
      {
        topic_name: "Runtime Python",
        preserve_answer_status: true,
        expected_version: 4,
        reason: "Уточнил тему",
      },
      expect.any(String),
    ),
  );
});

it("запускает генерацию отсутствующего AI-ответа прямо из проверки карточки", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "adminCardAutomationCluster").mockResolvedValue({
    ...clusterDetail,
    answer_contract: null,
    answer_validation: null,
    answer_status: "needs_expert_source",
  });
  const generate = vi
    .spyOn(api, "generateAdminCardAutomationClusterAnswer")
    .mockResolvedValue({
      cluster_id: cluster.id,
      version: cluster.version,
      job_id: "card-automation:answer-test",
    });

  renderPage(
    <AdminCardAutomationClusterDetailPage />,
    `/admin/card-automation/clusters/${cluster.id}`,
    "/admin/card-automation/clusters/:clusterId",
  );

  await user.click(
    await screen.findByRole("button", { name: "Сгенерировать AI-ответ" }),
  );

  await waitFor(() =>
    expect(generate).toHaveBeenCalledWith(
      cluster.id,
      { expected_version: cluster.version },
      expect.any(String),
    ),
  );
  expect(
    screen.getByRole("button", { name: "AI формирует ответ…" }),
  ).toBeDisabled();
});

it("показывает ошибку occurrence и безопасно запускает повторную обработку", async () => {
  const user = userEvent.setup();
  const failedOccurrence = {
    ...clusterDetail.occurrences[0]!,
    automation_status: "failed" as const,
    automation_revision: 5,
    automation_error: "answer_contract_failed: upstream timeout",
  };
  vi.spyOn(api, "mentorCardAutomationCluster").mockResolvedValue({
    ...clusterDetail,
    occurrences: [failedOccurrence],
  });
  const reprocess = vi
    .spyOn(api, "reprocessMentorCardAutomationOccurrence")
    .mockResolvedValue({
      question_id: failedOccurrence.id,
      revision: 5,
      job_id: "56000000-0000-4000-8000-000000000001",
    });
  vi.spyOn(window, "prompt").mockReturnValue("повтор после сбоя провайдера");
  vi.spyOn(window, "confirm").mockReturnValue(true);

  renderPage(
    <MentorCardAutomationClusterDetailPage />,
    `/mentor/card-automation/clusters/${cluster.id}`,
    "/mentor/card-automation/clusters/:clusterId",
  );

  await user.click(
    await screen.findByRole("tab", { name: /Исходные вопросы/ }),
  );
  expect(
    screen.getByText("answer_contract_failed: upstream timeout"),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Повторить обработку" }));

  await waitFor(() =>
    expect(reprocess).toHaveBeenCalledWith(
      failedOccurrence.id,
      {
        expected_revision: 5,
        reason: "повтор после сбоя провайдера",
      },
      expect.any(String),
    ),
  );
});

it("обслуживает audit решений ментора через mentor endpoints", async () => {
  const user = userEvent.setup();
  const failedDecision = {
    ...decision,
    decision_type: "answer_contract_failed" as const,
  };
  const adminTracks = vi.spyOn(api, "adminTracks").mockResolvedValue([]);
  const adminDecisions = vi
    .spyOn(api, "adminCardAutomationDecisions")
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  vi.spyOn(api, "mentorCardAutomationDecisions").mockResolvedValue({
    items: [failedDecision],
    total: 1,
    limit: 20,
    offset: 0,
  });
  const review = vi
    .spyOn(api, "reviewMentorCardAutomationDecision")
    .mockResolvedValue({ ...failedDecision, review_result: "correct" });

  renderPage(
    <MentorCardAutomationDecisionsPage />,
    "/mentor/card-automation/decisions",
    "/mentor/card-automation/decisions",
  );

  expect(
    (await screen.findAllByText("Не удалось сформировать контракт ответа"))
      .length,
  ).toBeGreaterThan(0);
  await user.click(
    screen.getByRole("button", { name: "Проверить техрешение" }),
  );
  await user.click(screen.getByRole("button", { name: "Сохранить проверку" }));

  await waitFor(() =>
    expect(review).toHaveBeenCalledWith(
      failedDecision.id,
      { result: "correct", reason: null },
      expect.any(String),
    ),
  );
  expect(adminDecisions).not.toHaveBeenCalled();
  expect(adminTracks).not.toHaveBeenCalled();
  expect(
    screen.queryByRole("tab", { name: "Метрики" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("tab", { name: "Настройки" }),
  ).not.toBeInTheDocument();
});

it("требует явное подтверждение bulk action и обновляет версии при конфликте", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "adminTracks").mockResolvedValue([]);
  const list = vi.spyOn(api, "adminCardAutomationClusters").mockResolvedValue({
    items: [cluster, secondCluster],
    total: 2,
    limit: 20,
    offset: 0,
  });
  const bulk = vi
    .spyOn(api, "bulkAdminCardAutomationClusters")
    .mockRejectedValue(
      new ApiError(409, "version_conflict", "Версии устарели"),
    );
  vi.spyOn(window, "confirm").mockReturnValue(true);

  renderPage(
    <AdminCardAutomationClustersPage />,
    "/admin/card-automation/clusters",
    "/admin/card-automation/clusters",
  );

  await user.click(
    await screen.findByLabelText("Выбрать все кластеры на странице"),
  );
  await user.click(screen.getByRole("button", { name: "Массовое действие" }));
  const dialog = await screen.findByRole("dialog", {
    name: "Массовое действие · 2 кластеров",
  });
  const actionSelect = within(dialog).getByLabelText("Действие");
  await user.click(actionSelect);
  await user.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}{Enter}");
  expect(actionSelect).toHaveValue("Исключить выбранный шум");
  await user.type(
    within(dialog).getByLabelText(/Причина/),
    "ручная проверка шума",
  );
  const submit = within(dialog).getByRole("button", {
    name: "Подтвердить массовое действие",
  });
  expect(submit).toBeDisabled();
  await user.click(
    within(dialog).getByLabelText("Я подтверждаю действие для 2 кластеров"),
  );
  await user.click(submit);

  await waitFor(() =>
    expect(bulk).toHaveBeenCalledWith(
      {
        action: "ignore_noise",
        cluster_ids: [cluster.id, secondCluster.id],
        expected_versions: {
          [cluster.id]: 4,
          [secondCluster.id]: 7,
        },
        confirmation: true,
        reason: "ручная проверка шума",
        card_id: null,
        topic_name: null,
      },
      expect.any(String),
    ),
  );
  await user.click(
    await screen.findByRole("button", { name: "Обновить кластеры" }),
  );
  expect(window.confirm).toHaveBeenCalledWith(
    "Закрыть форму, снять выбор и загрузить актуальные версии?",
  );
  await waitFor(() => expect(list.mock.calls.length).toBeGreaterThan(1));
});

it("без ошибки выбирает и снимает выбор отдельного кластера", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "adminTracks").mockResolvedValue([]);
  vi.spyOn(api, "adminCardAutomationClusters").mockResolvedValue({
    items: [cluster, secondCluster],
    total: 2,
    limit: 20,
    offset: 0,
  });

  renderPage(
    <AdminCardAutomationClustersPage />,
    "/admin/card-automation/clusters",
    "/admin/card-automation/clusters",
  );

  const checkbox = await screen.findByLabelText(
    `Выбрать кластер: ${cluster.canonical_question}`,
  );
  await user.click(checkbox);

  expect(screen.getByText("Выбрано кластеров: 1")).toBeInTheDocument();
  expect(checkbox).toBeChecked();

  await user.click(checkbox);

  expect(screen.getByText("Выбрано кластеров: 0")).toBeInTheDocument();
  expect(checkbox).not.toBeChecked();
});

it("поддерживает J/K/Enter и не перехватывает Enter в поле ввода", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "adminTracks").mockResolvedValue([]);
  vi.spyOn(api, "adminCardAutomationClusters").mockResolvedValue({
    items: [cluster, secondCluster],
    total: 2,
    limit: 20,
    offset: 0,
  });
  Object.defineProperty(window, "innerWidth", {
    configurable: true,
    value: 1280,
  });

  const view = renderPage(
    <AdminCardAutomationClustersPage />,
    "/admin/card-automation/clusters",
    "/admin/card-automation/clusters",
  );

  const topic = await screen.findByRole("textbox", { name: "Тема" });
  await user.click(topic);
  await user.keyboard("{Enter}");
  expect(view.router.state.location.pathname).toBe(
    "/admin/card-automation/clusters",
  );

  topic.blur();
  const secondRow = screen
    .getByText(secondCluster.canonical_question)
    .closest("tr");
  await user.keyboard("j");
  expect(secondRow).toHaveAttribute("aria-selected", "true");
  await user.keyboard("{Enter}");
  await waitFor(() =>
    expect(view.router.state.location.pathname).toBe(
      `/admin/card-automation/clusters/${secondCluster.id}`,
    ),
  );
});

it("показывает метрики за URL-период и передаёт admin-фильтры", async () => {
  vi.spyOn(api, "adminTracks").mockResolvedValue([]);
  const getMetrics = vi
    .spyOn(api, "adminCardAutomationMetrics")
    .mockResolvedValue(metrics);

  renderPage(
    <AdminCardAutomationMetricsPage />,
    `/admin/card-automation/metrics?period_from=2026-08-01&period_to=2026-08-16&direction_id=${directionId}`,
    "/admin/card-automation/metrics",
  );

  expect(await screen.findByText("Воронка автоматизации")).toBeInTheDocument();
  expect(screen.getByText("Ручная модерация")).toBeInTheDocument();
  expect(screen.getByText("Качество решений")).toBeInTheDocument();
  expect(screen.getByText("Стоимость AI")).toBeInTheDocument();
  expect(getMetrics).toHaveBeenCalledWith({
    periodFrom: "2026-08-01",
    periodTo: "2026-08-16",
    directionId,
  });
});

it("даёт ментору версионированно корректировать личный вопрос ученика", async () => {
  const user = userEvent.setup();
  const list = vi
    .spyOn(api, "mentorManagedPersonalReviewItems")
    .mockResolvedValue({
      items: [personalItem],
      total: 1,
      limit: 20,
      offset: 0,
    });
  const adminList = vi
    .spyOn(api, "adminManagedPersonalReviewItems")
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });
  const update = vi
    .spyOn(api, "updateMentorManagedPersonalReviewItem")
    .mockRejectedValue(
      new ApiError(
        409,
        "personal_review_item_version_conflict",
        "Версия устарела",
      ),
    );
  vi.spyOn(window, "confirm").mockReturnValue(true);

  renderPage(
    <MentorManagedPersonalReviewPage />,
    "/mentor/card-automation/students/student-1/personal-review",
    "/mentor/card-automation/students/:studentId/personal-review",
  );

  expect(
    await screen.findByText(personalItem.question_text),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Редактировать" }));
  const dialog = await screen.findByRole("dialog", {
    name: "Изменить личный вопрос",
  });
  const answer = within(dialog).getByLabelText("Краткий ответ");
  await user.clear(answer);
  await user.type(answer, "Уточнённый проверенный ответ");
  await user.type(
    within(dialog).getByLabelText(/Причина изменения/),
    "Проверено на созвоне",
  );
  await user.click(
    within(dialog).getByRole("button", { name: "Сохранить корректировку" }),
  );

  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      "student-1",
      personalItem.id,
      {
        expected_version: 3,
        reason: "Проверено на созвоне",
        answer_summary: "Уточнённый проверенный ответ",
      },
      expect.any(String),
    ),
  );
  await user.click(
    await within(dialog).findByRole("button", { name: "Обновить вопрос" }),
  );
  expect(window.confirm).toHaveBeenCalledWith(
    "Закрыть форму и загрузить актуальную версию вопроса?",
  );
  await waitFor(() => expect(list.mock.calls.length).toBeGreaterThan(1));
  expect(adminList).not.toHaveBeenCalled();
});

it("маршрутизирует admin personal-review ученика в admin API", async () => {
  const adminList = vi
    .spyOn(api, "adminManagedPersonalReviewItems")
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 20 });
  const mentorList = vi
    .spyOn(api, "mentorManagedPersonalReviewItems")
    .mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 });

  renderPage(
    <AdminManagedPersonalReviewPage />,
    "/admin/card-automation/students/student-1/personal-review?status=archived&due_only=true&due_before=2026-08-20&sort_order=desc&page=2",
    "/admin/card-automation/students/:studentId/personal-review",
  );

  expect(
    await screen.findByText("По этим фильтрам вопросов нет"),
  ).toBeInTheDocument();
  expect(adminList).toHaveBeenCalledWith(
    "student-1",
    {
      directionId: null,
      statuses: ["archived"],
      dueOnly: true,
      dueBefore: "2026-08-20T23:59:59.999Z",
      sortOrder: "desc",
    },
    { limit: 20, offset: 20 },
  );
  expect(mentorList).not.toHaveBeenCalled();
});

it("сохраняет выборочный аудит решения", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "adminTracks").mockResolvedValue([]);
  vi.spyOn(api, "adminCardAutomationDecisions").mockResolvedValue({
    items: [decision],
    total: 1,
    limit: 20,
    offset: 0,
  });
  const review = vi
    .spyOn(api, "reviewAdminCardAutomationDecision")
    .mockResolvedValue({ ...decision, review_result: "correct" });

  renderPage(
    <AdminCardAutomationDecisionsPage />,
    "/admin/card-automation/decisions",
    "/admin/card-automation/decisions",
  );

  await user.click(
    await screen.findByRole("button", { name: "Проверить техрешение" }),
  );
  await user.click(screen.getByRole("button", { name: "Сохранить проверку" }));

  await waitFor(() =>
    expect(review).toHaveBeenCalledWith(
      decision.id,
      { result: "correct", reason: null },
      expect.any(String),
    ),
  );
});

it("никогда не включает глобальную автопубликацию из настроек", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "adminCardAutomationSettings").mockResolvedValue({
    items: [settings],
  });
  const update = vi
    .spyOn(api, "updateAdminCardAutomationSettings")
    .mockResolvedValue({ ...settings, enabled: true, version: 5 });

  renderPage(
    <AdminCardAutomationSettingsPage />,
    "/admin/card-automation/settings",
    "/admin/card-automation/settings",
  );

  await user.click(await screen.findByText("Автоматизация включена"));
  await user.click(screen.getByRole("button", { name: "Сохранить настройки" }));

  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({
        direction_id: directionId,
        expected_version: 4,
        enabled: true,
        global_auto_publish_enabled: false,
      }),
      expect.any(String),
    ),
  );
  const globalPublishLabel = screen.getByText("Глобальная автопубликация");
  expect(
    globalPublishLabel.closest("label")?.querySelector("input"),
  ).toBeDisabled();
});

it("одной кнопкой включает только безопасный shadow-режим", async () => {
  const user = userEvent.setup();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  vi.spyOn(api, "adminCardAutomationSettings").mockResolvedValue({
    items: [settings],
  });
  const update = vi
    .spyOn(api, "updateAdminCardAutomationSettings")
    .mockResolvedValue({
      ...settings,
      enabled: true,
      shadow_mode: true,
      auto_ignore_noise_enabled: false,
      auto_link_exact_enabled: false,
      auto_link_alias_enabled: false,
      version: 5,
    });

  renderPage(
    <AdminCardAutomationSettingsPage />,
    "/admin/card-automation/settings",
    "/admin/card-automation/settings",
  );

  await user.click(
    await screen.findByRole("button", {
      name: "Включить безопасный shadow-режим",
    }),
  );

  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      expect.objectContaining({
        direction_id: directionId,
        expected_version: 4,
        enabled: true,
        shadow_mode: true,
        auto_ignore_noise_enabled: false,
        auto_link_exact_enabled: false,
        auto_link_alias_enabled: false,
        auto_link_semantic_enabled: false,
        personal_review_enabled: false,
        global_auto_publish_enabled: false,
        cluster_moderation_enabled: false,
        legacy_queue_enabled: true,
      }),
      expect.any(String),
    ),
  );
  expect(window.confirm).toHaveBeenCalled();
});

it("передаёт версию личного вопроса и предлагает обновление при конфликте", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "personalReviewItems").mockResolvedValue({
    items: [personalItem],
    total: 1,
    limit: 20,
    offset: 0,
  });
  const review = vi
    .spyOn(api, "reviewPersonalReviewItem")
    .mockRejectedValue(
      new ApiError(409, "version_conflict", "Версия устарела"),
    );
  vi.spyOn(window, "confirm").mockReturnValue(true);

  renderPage(
    <PersonalReviewPage />,
    "/interviews/personal-review",
    "/interviews/personal-review",
  );

  await user.click(
    await screen.findByRole("button", { name: "Показать ответ" }),
  );
  await user.click(screen.getByRole("button", { name: /Помню/ }));

  await waitFor(() =>
    expect(review).toHaveBeenCalledWith(
      personalItem.id,
      { rating: "good", expected_version: 3 },
      expect.any(String),
    ),
  );
  await user.click(
    await screen.findByRole("button", { name: "Обновить вопрос" }),
  );
  expect(window.confirm).toHaveBeenCalled();
});
