import {
  Accordion,
  Alert,
  Badge,
  Button,
  Card,
  Group,
  MultiSelect,
  NumberInput,
  Radio,
  Select,
  SimpleGrid,
  Stack,
  Tabs,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { CardAutomationNavigation } from "../features/cardAutomation/CardAutomationNavigation";
import {
  useCreateCardFromQuestionCluster,
  useGenerateQuestionClusterAnswer,
  useLinkQuestionCluster,
  useMergeQuestionCluster,
  useQuestionCluster,
  useReprocessQuestionOccurrence,
  useSetQuestionClusterState,
  useSplitQuestionCluster,
  useUpdateQuestionClusterDraft,
  type CardAutomationScope,
} from "../features/cardAutomation/queries";
import {
  answerStatusLabels,
  clusterStatusColors,
  clusterStatusLabels,
  decisionSourceLabels,
  decisionTypeLabels,
  judgeDecisionLabels,
  learningObjectLabels,
  percent,
} from "../features/cardAutomation/presentation";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import type {
  CardAutomationAnswerContract,
  QuestionClusterAction,
  QuestionClusterDetail,
} from "../types/api";

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

function requiredReason(action: string) {
  const value = window.prompt(`Укажите причину действия «${action}»`);
  return value?.trim() || null;
}

type ClusterDraftForm = {
  canonicalQuestion: string;
  topicName: string;
  subtopicName: string;
  shortAnswer: string;
  requiredPoints: string;
  optionalPoints: string;
  commonMistakes: string;
  unsupportedClaims: string;
  followUpQuestions: string;
  difficulty: CardAutomationAnswerContract["difficulty"];
  versionScope: string;
  sourceReferences: string;
  confidence: number | "";
};

type ClusterDraftTextField =
  | "canonicalQuestion"
  | "topicName"
  | "subtopicName"
  | "shortAnswer"
  | "requiredPoints"
  | "optionalPoints"
  | "commonMistakes"
  | "unsupportedClaims"
  | "followUpQuestions"
  | "versionScope"
  | "sourceReferences";

function listToInput(values: string[]) {
  return values.join("\n");
}

function inputToList(value: string) {
  return Array.from(
    new Set(
      value
        .split("\n")
        .map((item) => item.trim())
        .filter(Boolean),
    ),
  );
}

function normalizedTopic(value: string) {
  return value.trim().replace(/\s+/g, " ").toLocaleLowerCase("ru-RU");
}

function uniqueTopics(values: string[]) {
  const topics = new Map<string, string>();
  values.forEach((value) => {
    const normalized = normalizedTopic(value);
    if (normalized && !topics.has(normalized)) topics.set(normalized, value);
  });
  return Array.from(topics.values()).sort((left, right) =>
    left.localeCompare(right, "ru-RU"),
  );
}

function existingTopic(options: string[], value: string) {
  const normalized = normalizedTopic(value);
  return (
    options.find((option) => normalizedTopic(option) === normalized) ?? null
  );
}

function initialClusterDraft(cluster: QuestionClusterDetail): ClusterDraftForm {
  const answer = cluster.answer_contract;
  return {
    canonicalQuestion: cluster.canonical_question,
    topicName: cluster.topic_name ?? "",
    subtopicName: cluster.subtopic_name ?? "",
    shortAnswer: answer?.short_answer ?? "",
    requiredPoints: listToInput(answer?.required_points ?? []),
    optionalPoints: listToInput(answer?.optional_points ?? []),
    commonMistakes: listToInput(answer?.common_mistakes ?? []),
    unsupportedClaims: listToInput(answer?.unsupported_claims ?? []),
    followUpQuestions: listToInput(answer?.follow_up_questions ?? []),
    difficulty: answer?.difficulty ?? "middle",
    versionScope: listToInput(answer?.version_scope ?? []),
    sourceReferences: listToInput(answer?.source_references ?? []),
    confidence: answer?.confidence ?? "",
  };
}

function hasAnswerContractInput(draft: ClusterDraftForm) {
  return (
    typeof draft.confidence === "number" ||
    [
      draft.shortAnswer,
      draft.requiredPoints,
      draft.optionalPoints,
      draft.commonMistakes,
      draft.unsupportedClaims,
      draft.followUpQuestions,
      draft.versionScope,
      draft.sourceReferences,
    ].some((value) => Boolean(value.trim()))
  );
}

function answerContractFromDraft(
  draft: ClusterDraftForm,
): CardAutomationAnswerContract | null {
  if (!draft.shortAnswer.trim() || typeof draft.confidence !== "number")
    return null;
  return {
    short_answer: draft.shortAnswer.trim(),
    required_points: inputToList(draft.requiredPoints),
    optional_points: inputToList(draft.optionalPoints),
    common_mistakes: inputToList(draft.commonMistakes),
    unsupported_claims: inputToList(draft.unsupportedClaims),
    follow_up_questions: inputToList(draft.followUpQuestions),
    difficulty: draft.difficulty,
    version_scope: inputToList(draft.versionScope),
    source_references: inputToList(draft.sourceReferences),
    confidence: draft.confidence,
  };
}

function ClusterDetail({
  cluster,
  reload,
  scope,
}: {
  cluster: QuestionClusterDetail;
  reload: () => Promise<unknown>;
  scope: CardAutomationScope;
}) {
  const location = useLocation();
  const link = useLinkQuestionCluster();
  const create = useCreateCardFromQuestionCluster();
  const generateAnswer = useGenerateQuestionClusterAnswer();
  const updateDraft = useUpdateQuestionClusterDraft(scope);
  const split = useSplitQuestionCluster();
  const merge = useMergeQuestionCluster();
  const setState = useSetQuestionClusterState(scope);
  const reprocess = useReprocessQuestionOccurrence(scope);
  const [selectedCardId, setSelectedCardId] = useState<string | null>(
    cluster.best_match?.card_id ?? null,
  );
  const availableDecks = cluster.topic_options;
  const clusterDeck = availableDecks.find(
    (deck) => deck.deck_id === cluster.deck_id,
  );
  const broadTopics = useMemo(
    () =>
      uniqueTopics(
        clusterDeck?.topics ?? availableDecks.flatMap((deck) => deck.topics),
      ),
    [availableDecks, clusterDeck],
  );
  const [initialDraft] = useState(() => ({
    deckId:
      cluster.deck_id ??
      availableDecks.find((deck) =>
        deck.topics.some(
          (topic) =>
            normalizedTopic(topic) ===
            normalizedTopic(cluster.topic_name ?? ""),
        ),
      )?.deck_id ??
      availableDecks[0]?.deck_id ??
      null,
    category: cluster.topic_name ?? cluster.topic_candidates[0] ?? "",
    subcategory: cluster.subtopic_name ?? "",
    question: cluster.canonical_question,
    answer: cluster.answer_contract?.short_answer ?? "",
  }));
  const [deckId, setDeckId] = useState<string | null>(initialDraft.deckId);
  const [category, setCategory] = useState(initialDraft.category);
  const [subcategory, setSubcategory] = useState(initialDraft.subcategory);
  const [question, setQuestion] = useState(initialDraft.question);
  const [answer, setAnswer] = useState(initialDraft.answer);
  const [answerGenerationRequested, setAnswerGenerationRequested] =
    useState(false);
  const [initialReviewedDraft] = useState(() => initialClusterDraft(cluster));
  const [reviewedDraft, setReviewedDraft] =
    useState<ClusterDraftForm>(initialReviewedDraft);
  const updateReviewedDraftText = (
    field: ClusterDraftTextField,
    value: string,
  ) => {
    setReviewedDraft((current) => ({ ...current, [field]: value }));
  };
  const [draftReason, setDraftReason] = useState("");
  const [splitOccurrenceIds, setSplitOccurrenceIds] = useState<string[]>([]);
  const [splitQuestion, setSplitQuestion] = useState("");
  const [splitTopic, setSplitTopic] = useState("");
  const [splitSubtopic, setSplitSubtopic] = useState("");
  const [mergeClusterId, setMergeClusterId] = useState("");
  const [mergeClusterVersion, setMergeClusterVersion] = useState<number | "">(
    "",
  );
  const mutation =
    link.isPending ||
    create.isPending ||
    generateAnswer.isPending ||
    updateDraft.isPending ||
    split.isPending ||
    merge.isPending ||
    setState.isPending ||
    reprocess.isPending;
  const mutationError =
    link.error ??
    create.error ??
    generateAnswer.error ??
    updateDraft.error ??
    split.error ??
    merge.error ??
    setState.error ??
    reprocess.error;
  const selectedDeck = availableDecks.find((deck) => deck.deck_id === deckId);
  const selectedDeckTopics = useMemo(
    () => uniqueTopics(selectedDeck?.topics ?? []),
    [selectedDeck],
  );
  const selectedCreateTopic = existingTopic(selectedDeckTopics, category);
  const selectedSplitTopic = existingTopic(broadTopics, splitTopic);

  useEffect(() => {
    if (!answerGenerationRequested || cluster.answer_contract !== null) return;
    const timer = window.setInterval(() => void reload(), 2_500);
    return () => window.clearInterval(timer);
  }, [answerGenerationRequested, cluster.answer_contract, reload]);

  useEffect(() => {
    const generatedAnswer = cluster.answer_contract?.short_answer.trim();
    if (!answerGenerationRequested || !generatedAnswer) return;
    setAnswer(generatedAnswer);
    setAnswerGenerationRequested(false);
  }, [answerGenerationRequested, cluster.answer_contract]);

  useEffect(() => {
    if (availableDecks.length === 0) return;
    const nextDeck =
      availableDecks.find((deck) => deck.deck_id === deckId) ??
      availableDecks[0];
    if (!nextDeck) return;
    if (nextDeck.deck_id !== deckId) setDeckId(nextDeck.deck_id);
    const options = uniqueTopics(nextDeck.topics);
    const nextTopic =
      existingTopic(options, category) ??
      existingTopic(options, cluster.topic_name ?? "") ??
      "";
    if (nextTopic !== category) setCategory(nextTopic);
  }, [availableDecks, category, cluster.topic_name, deckId]);
  const conflict =
    mutationError instanceof ApiError && mutationError.status === 409;
  const reviewedFormDirty =
    JSON.stringify(reviewedDraft) !== JSON.stringify(initialReviewedDraft);
  const answerContractStarted = hasAnswerContractInput(reviewedDraft);
  const reviewedAnswerContract = answerContractFromDraft(reviewedDraft);
  const answerContractValid =
    (!answerContractStarted && cluster.answer_contract === null) ||
    reviewedAnswerContract !== null;
  const canonicalQuestionChanged =
    reviewedDraft.canonicalQuestion.trim() !== cluster.canonical_question;
  const reviewedTopicName = existingTopic(broadTopics, reviewedDraft.topicName);
  const topicNameChanged =
    reviewedTopicName !== null && reviewedTopicName !== cluster.topic_name;
  const reviewedSubtopicName = reviewedDraft.subtopicName.trim() || null;
  const subtopicNameChanged = reviewedSubtopicName !== cluster.subtopic_name;
  const answerContractChanged =
    reviewedAnswerContract !== null &&
    JSON.stringify(reviewedAnswerContract) !==
      JSON.stringify(cluster.answer_contract);
  const reviewedDraftChanged =
    canonicalQuestionChanged ||
    topicNameChanged ||
    subtopicNameChanged ||
    answerContractChanged;
  const proposalQuestionChanged =
    question.trim() !== cluster.canonical_question;
  const proposalTopicChanged =
    selectedCreateTopic !== null && selectedCreateTopic !== cluster.topic_name;
  const proposalSubtopic = subcategory.trim() || null;
  const proposalSubtopicChanged = proposalSubtopic !== cluster.subtopic_name;
  const proposalAnswerChanged =
    answer.trim() !== (cluster.answer_contract?.short_answer ?? "");
  const proposalChanged =
    proposalQuestionChanged ||
    proposalTopicChanged ||
    proposalSubtopicChanged ||
    proposalAnswerChanged;
  useUnsavedChanges(
    deckId !== initialDraft.deckId ||
      category !== initialDraft.category ||
      subcategory !== initialDraft.subcategory ||
      question !== initialDraft.question ||
      answer !== initialDraft.answer ||
      reviewedFormDirty ||
      Boolean(draftReason.trim()) ||
      splitOccurrenceIds.length > 0 ||
      Boolean(
        splitQuestion.trim() || splitTopic.trim() || splitSubtopic.trim(),
      ) ||
      Boolean(mergeClusterId.trim()) ||
      mergeClusterVersion !== "",
  );
  const mentorActions = new Set<QuestionClusterAction>([
    "update_draft",
    "ignore",
    "defer",
    "mark_important",
    "reopen",
  ]);
  const can = (action: QuestionClusterAction) =>
    cluster.allowed_actions.includes(action) &&
    (scope === "admin" || mentorActions.has(action));

  const notifySuccess = (message: string) =>
    notifications.show({ color: "green", message });
  const notifyError = (error: Error) =>
    notifications.show({ color: "red", message: error.message });

  const linkCard = () => {
    const candidate = cluster.top_card_matches.find(
      (item) => item.card_id === selectedCardId,
    );
    if (!candidate) return;
    const reason = requiredReason("связать с карточкой");
    if (
      !reason ||
      !window.confirm(
        `Связать весь кластер с карточкой «${candidate.question_markdown}»?`,
      )
    )
      return;
    link.mutate(
      {
        clusterId: cluster.id,
        payload: {
          card_id: candidate.card_id,
          confirm_alias: true,
          expected_version: cluster.version,
          reason,
        },
      },
      {
        onSuccess: () => notifySuccess("Кластер связан с карточкой"),
        onError: notifyError,
      },
    );
  };

  const createCard = () => {
    if (!deckId || !selectedCreateTopic || !question.trim() || !answer.trim())
      return;
    const reason = requiredReason(
      "принять AI-предложение и создать каноническую карточку",
    );
    if (
      !reason ||
      !window.confirm(
        "Принять AI-предложение и создать одну каноническую карточку в общей базе? Это отдельное ручное действие, автопубликация не включается.",
      )
    )
      return;
    create.mutate(
      {
        clusterId: cluster.id,
        payload: {
          deck_id: deckId,
          category: selectedCreateTopic,
          subcategory: subcategory.trim() || null,
          question_markdown: question.trim(),
          answer_markdown: answer.trim(),
          frequency: "occasional",
          frequency_mode: "automatic",
          expected_version: cluster.version,
          reason,
        },
      },
      {
        onSuccess: () =>
          notifySuccess(
            "AI-предложение принято, каноническая карточка создана",
          ),
        onError: notifyError,
      },
    );
  };

  const saveProposalDraft = () => {
    if (
      !can("update_draft") ||
      !proposalChanged ||
      !selectedCreateTopic ||
      !question.trim()
    )
      return;
    const reason = requiredReason("сохранить исправления AI-предложения");
    if (!reason) return;
    const answerContract = answer.trim()
      ? {
          ...(cluster.answer_contract ?? {
            required_points: [],
            optional_points: [],
            common_mistakes: [],
            unsupported_claims: [
              "Ответ отредактирован модератором и требует финального подтверждения.",
            ],
            follow_up_questions: [],
            difficulty: "mixed" as const,
            version_scope: [],
            source_references: [],
            confidence: 0.5,
          }),
          short_answer: answer.trim(),
        }
      : null;
    updateDraft.mutate(
      {
        clusterId: cluster.id,
        payload: {
          ...(proposalQuestionChanged
            ? { canonical_question: question.trim() }
            : {}),
          ...(proposalTopicChanged ? { topic_name: selectedCreateTopic } : {}),
          ...(proposalSubtopicChanged
            ? { subtopic_name: proposalSubtopic }
            : {}),
          ...(proposalAnswerChanged && answerContract
            ? { answer_contract: answerContract }
            : {}),
          preserve_answer_status:
            !proposalQuestionChanged && !proposalAnswerChanged,
          expected_version: cluster.version,
          reason,
        },
      },
      {
        onSuccess: () => notifySuccess("Исправления карточки сохранены"),
        onError: notifyError,
      },
    );
  };

  const requestAnswerGeneration = () => {
    generateAnswer.mutate(
      {
        clusterId: cluster.id,
        payload: { expected_version: cluster.version },
      },
      {
        onSuccess: () => {
          setAnswerGenerationRequested(true);
          notifySuccess("AI формирует черновик ответа");
          void reload();
        },
        onError: notifyError,
      },
    );
  };

  const saveReviewedDraft = () => {
    if (
      !reviewedDraftChanged ||
      !reviewedDraft.canonicalQuestion.trim() ||
      !reviewedTopicName ||
      !answerContractValid ||
      !draftReason.trim()
    )
      return;
    updateDraft.mutate(
      {
        clusterId: cluster.id,
        payload: {
          ...(canonicalQuestionChanged
            ? { canonical_question: reviewedDraft.canonicalQuestion.trim() }
            : {}),
          ...(topicNameChanged ? { topic_name: reviewedTopicName } : {}),
          ...(subtopicNameChanged
            ? { subtopic_name: reviewedSubtopicName }
            : {}),
          ...(answerContractChanged && reviewedAnswerContract
            ? { answer_contract: reviewedAnswerContract }
            : {}),
          preserve_answer_status:
            !canonicalQuestionChanged && !answerContractChanged,
          expected_version: cluster.version,
          reason: draftReason.trim(),
        },
      },
      {
        onSuccess: () =>
          notifySuccess(
            "Проверенный черновик сохранён без создания общей карточки",
          ),
        onError: notifyError,
      },
    );
  };

  const runStateAction = (
    action: "ignore" | "defer" | "mark-important" | "reopen",
    label: string,
  ) => {
    const reason = requiredReason(label);
    if (!reason || !window.confirm(`${label}? Изменение попадёт в аудит.`))
      return;
    setState.mutate(
      {
        clusterId: cluster.id,
        action,
        payload: { expected_version: cluster.version, reason },
      },
      {
        onSuccess: () => notifySuccess("Состояние кластера обновлено"),
        onError: notifyError,
      },
    );
  };

  const splitCluster = () => {
    if (
      splitOccurrenceIds.length === 0 ||
      splitOccurrenceIds.length === cluster.occurrences.length ||
      !splitQuestion.trim() ||
      !selectedSplitTopic
    )
      return;
    const reason = requiredReason("разделить кластер");
    if (
      !reason ||
      !window.confirm("Перенести выбранные появления в новый кластер?")
    )
      return;
    split.mutate(
      {
        clusterId: cluster.id,
        payload: {
          occurrence_ids: splitOccurrenceIds,
          new_canonical_question: splitQuestion.trim(),
          new_topic_name: selectedSplitTopic,
          new_subtopic_name: splitSubtopic.trim() || null,
          expected_version: cluster.version,
          reason,
        },
      },
      {
        onSuccess: () => {
          setSplitOccurrenceIds([]);
          notifySuccess("Кластер разделён");
        },
        onError: notifyError,
      },
    );
  };

  const reprocessOccurrence = (
    occurrenceId: string,
    expectedRevision: number,
  ) => {
    const reason = requiredReason("повторить обработку вопроса");
    if (
      !reason ||
      !window.confirm(
        "Поставить вопрос в очередь повторной обработки? Действие попадёт в аудит.",
      )
    )
      return;
    reprocess.mutate(
      {
        clusterId: cluster.id,
        occurrenceId,
        payload: { expected_revision: expectedRevision, reason },
      },
      {
        onSuccess: () =>
          notifySuccess("Вопрос поставлен в очередь повторной обработки"),
        onError: notifyError,
      },
    );
  };

  const mergeCluster = () => {
    if (!mergeClusterId.trim() || typeof mergeClusterVersion !== "number")
      return;
    const reason = requiredReason("объединить кластеры");
    if (
      !reason ||
      !window.confirm(
        "Объединить эти кластеры без физического удаления истории?",
      )
    )
      return;
    merge.mutate(
      {
        clusterId: cluster.id,
        payload: {
          target_cluster_id: mergeClusterId.trim(),
          target_expected_version: mergeClusterVersion,
          expected_version: cluster.version,
          reason,
        },
      },
      {
        onSuccess: () => notifySuccess("Кластеры объединены"),
        onError: notifyError,
      },
    );
  };

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-start">
        <PageHeader
          eyebrow={`${cluster.direction_title} · проверка карточки`}
          title={cluster.canonical_question}
          description="Проверьте тему, формулировку, ответ и возможное совпадение с существующей карточкой."
        />
        <Button
          component={Link}
          to={`/${scope}/card-automation/clusters${location.search}`}
          variant="light"
        >
          К очереди
        </Button>
      </Group>
      <CardAutomationNavigation scope={scope} />

      {mutationError && (
        <Alert
          color={conflict ? "yellow" : "red"}
          title={
            conflict
              ? "Кластер уже изменён другим пользователем"
              : "Не удалось выполнить действие"
          }
        >
          <Stack align="flex-start" gap="sm">
            <Text>{mutationError.message}</Text>
            {conflict && (
              <Button
                variant="light"
                onClick={() => {
                  if (
                    !window.confirm(
                      "Загрузить актуальную версию? Несохранённые поля формы будут сброшены.",
                    )
                  )
                    return;
                  link.reset();
                  create.reset();
                  generateAnswer.reset();
                  updateDraft.reset();
                  split.reset();
                  merge.reset();
                  setState.reset();
                  reprocess.reset();
                  void reload();
                }}
              >
                Загрузить актуальную версию
              </Button>
            )}
          </Stack>
        </Alert>
      )}

      <Tabs defaultValue="answer" keepMounted={false}>
        <Tabs.List className="responsive-tabs">
          <Tabs.Tab value="answer">Проверка карточки</Tabs.Tab>
          <Tabs.Tab value="occurrences">
            Исходные вопросы ({cluster.occurrences.length})
          </Tabs.Tab>
          {scope === "admin" && can("update_draft") && (
            <Tabs.Tab value="draft">Расширенная правка</Tabs.Tab>
          )}
          <Tabs.Tab value="overview">Технические детали</Tabs.Tab>
          <Tabs.Tab value="history">История</Tabs.Tab>
        </Tabs.List>

        <Tabs.Panel value="overview" pt="lg">
          <Stack>
            <Group gap="xs">
              <Badge color={clusterStatusColors[cluster.status]}>
                {clusterStatusLabels[cluster.status]}
              </Badge>
              <Badge variant="outline">
                {learningObjectLabels[cluster.learning_object_type]}
              </Badge>
              <Badge variant="outline">
                Confidence: {percent(cluster.cluster_confidence)}
              </Badge>
              <Badge variant="outline">
                Priority: {cluster.priority_score.toFixed(2)}
              </Badge>
              {cluster.manual_important && <Badge color="red">Важный</Badge>}
            </Group>
            <SimpleGrid cols={{ base: 2, md: 5 }}>
              {[
                ["Появлений", cluster.occurrences_count],
                ["Интервью", cluster.distinct_interviews_count],
                ["Компаний", cluster.distinct_companies_count],
                ["Учеников", cluster.distinct_students_count],
                ["Плохих ответов", cluster.failed_answers_count],
              ].map(([label, value]) => (
                <Card key={String(label)} withBorder>
                  <Text className="technical-label">{label}</Text>
                  <Title order={2}>{value}</Title>
                </Card>
              ))}
            </SimpleGrid>
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <Card withBorder>
                <Stack>
                  <Title order={3}>Варианты формулировок</Title>
                  {cluster.question_variants.length === 0 ? (
                    <Text c="dimmed">Вариантов пока нет.</Text>
                  ) : (
                    cluster.question_variants.map((variant) => (
                      <div key={variant.normalized_question_text}>
                        <Text fw={600}>{variant.question_text}</Text>
                        <Text size="xs" c="dimmed">
                          {variant.occurrences_count} появлений · последнее{" "}
                          {formatDate(variant.last_seen_at)}
                        </Text>
                      </div>
                    ))
                  )}
                </Stack>
              </Card>
              <Card withBorder>
                <Stack>
                  <Title order={3}>Покрытие</Title>
                  <Text>
                    Компании:{" "}
                    {cluster.companies
                      .map((item) => item.company_name)
                      .join(", ") || "—"}
                  </Text>
                  <Text>
                    Широкая тема: {cluster.topic_name ?? "Не определена"}
                  </Text>
                  {cluster.subtopic_name && (
                    <Text>Подтема: {cluster.subtopic_name}</Text>
                  )}
                  {cluster.promotion_reason && (
                    <Text size="sm" c="dimmed">
                      Причина продвижения: {cluster.promotion_reason}
                    </Text>
                  )}
                </Stack>
              </Card>
            </SimpleGrid>
          </Stack>
        </Tabs.Panel>

        {scope === "admin" && can("update_draft") && (
          <Tabs.Panel value="draft" pt="lg">
            <Card withBorder>
              <Stack>
                <div>
                  <Group justify="space-between" align="flex-start">
                    <Title order={3}>Проверенный черновик кластера</Title>
                    <Badge variant="outline">Версия {cluster.version}</Badge>
                  </Group>
                  <Text size="sm" c="dimmed" mt={4}>
                    Проверьте предложение AI до публикации. Сохранение изменяет
                    только черновик кластера — общая карточка не создаётся и не
                    публикуется автоматически.
                  </Text>
                </div>

                <Textarea
                  label="Канонический вопрос"
                  description="Одна точная проверяемая идея без привязки к конкретному собеседованию."
                  minRows={3}
                  required
                  value={reviewedDraft.canonicalQuestion}
                  onChange={(event) =>
                    updateReviewedDraftText(
                      "canonicalQuestion",
                      event.currentTarget.value,
                    )
                  }
                />
                {!existingTopic(broadTopics, reviewedDraft.topicName) &&
                  reviewedDraft.topicName && (
                    <Alert color="yellow" title="Нужно выбрать широкую тему">
                      Текущее AI-предложение «{reviewedDraft.topicName}» не
                      совпадает с существующей темой карточек. Оно не будет
                      создано как новая тема автоматически.
                    </Alert>
                  )}
                <Select
                  label="Широкая тема"
                  description="Определяет группировку карточек для учеников. Можно выбрать только существующую тему."
                  placeholder="Выберите тему из базы карточек"
                  required
                  searchable
                  allowDeselect={false}
                  data={broadTopics}
                  value={existingTopic(broadTopics, reviewedDraft.topicName)}
                  onChange={(value) =>
                    value && updateReviewedDraftText("topicName", value)
                  }
                  nothingFoundMessage="В этом направлении пока нет тем"
                />
                <TextInput
                  label="Детальная подтема"
                  description="Необязательно. Уточняет содержание, но не создаёт новую группу карточек."
                  value={reviewedDraft.subtopicName}
                  onChange={(event) =>
                    updateReviewedDraftText(
                      "subtopicName",
                      event.currentTarget.value,
                    )
                  }
                />
                <Textarea
                  label="Краткий проверенный ответ"
                  minRows={5}
                  required={
                    cluster.answer_contract !== null || answerContractStarted
                  }
                  value={reviewedDraft.shortAnswer}
                  onChange={(event) =>
                    updateReviewedDraftText(
                      "shortAnswer",
                      event.currentTarget.value,
                    )
                  }
                />

                <SimpleGrid cols={{ base: 1, md: 2 }}>
                  <Textarea
                    label="Обязательные пункты"
                    description="Один пункт на строку."
                    minRows={5}
                    value={reviewedDraft.requiredPoints}
                    onChange={(event) =>
                      updateReviewedDraftText(
                        "requiredPoints",
                        event.currentTarget.value,
                      )
                    }
                  />
                  <Textarea
                    label="Дополнительные пункты"
                    description="Один пункт на строку."
                    minRows={5}
                    value={reviewedDraft.optionalPoints}
                    onChange={(event) =>
                      updateReviewedDraftText(
                        "optionalPoints",
                        event.currentTarget.value,
                      )
                    }
                  />
                  <Textarea
                    label="Типичные ошибки"
                    description="Одна ошибка на строку."
                    minRows={4}
                    value={reviewedDraft.commonMistakes}
                    onChange={(event) =>
                      updateReviewedDraftText(
                        "commonMistakes",
                        event.currentTarget.value,
                      )
                    }
                  />
                  <Textarea
                    label="Неподтверждённые утверждения"
                    description="Одно утверждение на строку."
                    minRows={4}
                    value={reviewedDraft.unsupportedClaims}
                    onChange={(event) =>
                      updateReviewedDraftText(
                        "unsupportedClaims",
                        event.currentTarget.value,
                      )
                    }
                  />
                  <Textarea
                    label="Уточняющие вопросы"
                    description="Один вопрос на строку."
                    minRows={4}
                    value={reviewedDraft.followUpQuestions}
                    onChange={(event) =>
                      updateReviewedDraftText(
                        "followUpQuestions",
                        event.currentTarget.value,
                      )
                    }
                  />
                  <Textarea
                    label="Область версий"
                    description="Например, CPython 3.12. Одно значение на строку."
                    minRows={4}
                    value={reviewedDraft.versionScope}
                    onChange={(event) =>
                      updateReviewedDraftText(
                        "versionScope",
                        event.currentTarget.value,
                      )
                    }
                  />
                </SimpleGrid>

                <Textarea
                  label="Подтверждающие источники"
                  description="Одна внутренняя или разрешённая ссылка на строку."
                  minRows={3}
                  value={reviewedDraft.sourceReferences}
                  onChange={(event) =>
                    updateReviewedDraftText(
                      "sourceReferences",
                      event.currentTarget.value,
                    )
                  }
                />
                <SimpleGrid cols={{ base: 1, sm: 2 }}>
                  <Select
                    label="Уровень сложности"
                    required
                    value={reviewedDraft.difficulty}
                    data={[
                      { value: "junior", label: "Junior" },
                      { value: "middle", label: "Middle" },
                      { value: "senior", label: "Senior" },
                      { value: "mixed", label: "Смешанный" },
                    ]}
                    onChange={(value) =>
                      value &&
                      setReviewedDraft((current) => ({
                        ...current,
                        difficulty:
                          value as CardAutomationAnswerContract["difficulty"],
                      }))
                    }
                  />
                  <NumberInput
                    label="Уверенность ответа"
                    description="Значение от 0 до 1."
                    min={0}
                    max={1}
                    step={0.01}
                    decimalScale={2}
                    required={answerContractStarted}
                    value={reviewedDraft.confidence}
                    onChange={(value) =>
                      setReviewedDraft((current) => ({
                        ...current,
                        confidence: typeof value === "number" ? value : "",
                      }))
                    }
                  />
                </SimpleGrid>
                <Textarea
                  label="Причина изменения"
                  description="Обязательна для аудита: укажите, что и почему проверили вручную."
                  minRows={2}
                  required
                  value={draftReason}
                  onChange={(event) =>
                    setDraftReason(event.currentTarget.value)
                  }
                />
                <Group justify="space-between" align="center">
                  <Text size="sm" c="dimmed">
                    Изменение смысла вопроса или контракта ответа переведёт
                    ответ в статус «Требуется ручная проверка». Изменение только
                    темы сохранит текущий статус валидации.
                  </Text>
                  <Button
                    loading={updateDraft.isPending}
                    disabled={
                      mutation ||
                      !reviewedDraftChanged ||
                      !reviewedDraft.canonicalQuestion.trim() ||
                      !reviewedTopicName ||
                      !answerContractValid ||
                      !draftReason.trim() ||
                      updateDraft.isPending
                    }
                    onClick={saveReviewedDraft}
                  >
                    Сохранить проверенный черновик
                  </Button>
                </Group>
              </Stack>
            </Card>
          </Tabs.Panel>
        )}

        <Tabs.Panel value="occurrences" pt="lg">
          <Stack>
            {cluster.occurrences.map((occurrence) => (
              <Card key={occurrence.id} withBorder>
                <Stack gap="sm">
                  <Group justify="space-between" align="flex-start">
                    <div>
                      <Text fw={700}>{occurrence.question_text}</Text>
                      <Text size="xs" c="dimmed">
                        {occurrence.company_name} · {occurrence.student_name} ·{" "}
                        {formatDate(occurrence.interviewed_at)}
                      </Text>
                    </div>
                    <Badge variant="outline">
                      Routing: {percent(occurrence.routing_confidence)}
                    </Badge>
                  </Group>
                  {occurrence.source_context && (
                    <Text size="sm" style={{ whiteSpace: "pre-wrap" }}>
                      {occurrence.source_context}
                    </Text>
                  )}
                  {occurrence.answer_text && (
                    <Alert color="gray" title="Ответ кандидата">
                      {occurrence.answer_text}
                    </Alert>
                  )}
                  {occurrence.quality_flags.length > 0 && (
                    <Group gap="xs">
                      {occurrence.quality_flags.map((flag) => (
                        <Badge key={flag} color="yellow">
                          {flag}
                        </Badge>
                      ))}
                    </Group>
                  )}
                  {occurrence.automation_status === "failed" && (
                    <Alert color="red" title="Ошибка автоматической обработки">
                      <Stack align="flex-start" gap="sm">
                        <Text size="sm">
                          {occurrence.automation_error ??
                            "Причина ошибки не была сохранена."}
                        </Text>
                        <Button
                          size="xs"
                          variant="light"
                          color="red"
                          loading={
                            reprocess.isPending &&
                            reprocess.variables?.occurrenceId === occurrence.id
                          }
                          disabled={mutation}
                          onClick={() =>
                            reprocessOccurrence(
                              occurrence.id,
                              occurrence.automation_revision,
                            )
                          }
                        >
                          Повторить обработку
                        </Button>
                      </Stack>
                    </Alert>
                  )}
                </Stack>
              </Card>
            ))}
            {scope === "admin" &&
              can("split") &&
              cluster.occurrences.length > 1 && (
                <Card withBorder>
                  <Stack>
                    <Title order={3}>Разделить кластер</Title>
                    <MultiSelect
                      label="Появления для нового кластера"
                      value={splitOccurrenceIds}
                      onChange={setSplitOccurrenceIds}
                      data={cluster.occurrences.map((occurrence) => ({
                        value: occurrence.id,
                        label: `${occurrence.company_name}: ${occurrence.question_text}`,
                      }))}
                      searchable
                    />
                    <TextInput
                      label="Новый канонический вопрос"
                      value={splitQuestion}
                      onChange={(event) =>
                        setSplitQuestion(event.currentTarget.value)
                      }
                    />
                    <Select
                      label="Широкая тема нового кластера"
                      description="Только из существующих тем карточек направления."
                      placeholder="Выберите тему"
                      required
                      searchable
                      allowDeselect={false}
                      data={broadTopics}
                      value={selectedSplitTopic}
                      onChange={(value) => value && setSplitTopic(value)}
                    />
                    <TextInput
                      label="Детальная подтема нового кластера"
                      value={splitSubtopic}
                      onChange={(event) =>
                        setSplitSubtopic(event.currentTarget.value)
                      }
                    />
                    <Button
                      color="orange"
                      variant="light"
                      loading={split.isPending}
                      disabled={
                        mutation ||
                        !splitQuestion.trim() ||
                        !selectedSplitTopic ||
                        splitOccurrenceIds.length === 0 ||
                        splitOccurrenceIds.length === cluster.occurrences.length
                      }
                      onClick={splitCluster}
                    >
                      Разделить выбранные появления
                    </Button>
                  </Stack>
                </Card>
              )}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="answer" pt="lg">
          <Stack>
            <Alert color="blue" title="Что нужно проверить">
              <Text size="sm">
                AI уже собрал предложение карточки. Проверьте широкую тему,
                формулировку вопроса и ответ, затем убедитесь, что такой
                карточки ещё нет в базе. Любое поле можно исправить до
                публикации.
              </Text>
            </Alert>
            <Group gap="xs">
              <Badge variant="light">
                {cluster.occurrences_count} появлений
              </Badge>
              <Badge variant="light">
                {cluster.distinct_companies_count} компаний
              </Badge>
              {cluster.answer_status && (
                <Badge
                  color={
                    cluster.answer_status === "needs_expert_source"
                      ? "yellow"
                      : "blue"
                  }
                >
                  {answerStatusLabels[cluster.answer_status]}
                </Badge>
              )}
            </Group>

            <Card withBorder style={{ order: 2 }}>
              <Stack>
                <div>
                  <Title order={3}>4. Проверьте возможный дубль</Title>
                  <Text size="sm" c="dimmed" mt={4}>
                    Если существующая карточка проверяет тот же объём знаний,
                    свяжите вопрос с ней. Иначе создайте новую карточку ниже.
                  </Text>
                </div>
                {cluster.top_card_matches.length === 0 ? (
                  <Alert color="green" title="Похожих карточек не найдено">
                    Можно проверять и создавать новую карточку.
                  </Alert>
                ) : (
                  <Radio.Group
                    label="Похожие карточки"
                    value={selectedCardId ?? ""}
                    onChange={setSelectedCardId}
                  >
                    <Stack mt="sm">
                      {cluster.top_card_matches.map((candidate) => (
                        <Radio.Card
                          key={candidate.card_id}
                          value={candidate.card_id}
                          withBorder
                          p="md"
                          radius="md"
                        >
                          <Group wrap="nowrap" align="flex-start">
                            <Radio.Indicator />
                            <Stack gap="xs" style={{ flex: 1 }}>
                              <Group justify="space-between" align="flex-start">
                                <Text fw={700}>
                                  {candidate.question_markdown}
                                </Text>
                                <Badge variant="light">
                                  {percent(candidate.semantic_score)} похоже
                                </Badge>
                              </Group>
                              <Group gap="xs">
                                <Badge variant="outline">
                                  {candidate.category}
                                </Badge>
                                {cluster.linked_card_id ===
                                  candidate.card_id && (
                                  <Badge color="green">
                                    Уже связано системой
                                  </Badge>
                                )}
                                {candidate.judge_decision && (
                                  <Badge variant="light" color="blue">
                                    AI:{" "}
                                    {
                                      judgeDecisionLabels[
                                        candidate.judge_decision
                                      ]
                                    }
                                  </Badge>
                                )}
                              </Group>
                              <Text
                                size="sm"
                                style={{ whiteSpace: "pre-wrap" }}
                              >
                                {candidate.answer_markdown}
                              </Text>
                              {candidate.judge_reason && (
                                <Text size="xs" c="dimmed">
                                  {candidate.judge_reason}
                                </Text>
                              )}
                            </Stack>
                          </Group>
                        </Radio.Card>
                      ))}
                    </Stack>
                  </Radio.Group>
                )}
              </Stack>
            </Card>
            {(can("update_draft") ||
              (scope === "admin" && can("create_card"))) && (
              <Card withBorder style={{ order: 1 }}>
                <Stack>
                  <div>
                    <Title order={3}>Предложение AI</Title>
                    <Text size="sm" c="dimmed" mt={4}>
                      Ниже — итог автоматического разбора. Исправьте всё, с чем
                      не согласны. Изменения попадут в карточку только после
                      вашего подтверждения.
                    </Text>
                  </div>
                  {availableDecks.length === 0 && (
                    <Alert color="red">
                      Для направления нет опубликованной колоды с существующими
                      темами. Сначала добавьте хотя бы одну карточку в нужную
                      широкую тему.
                    </Alert>
                  )}
                  {scope === "admin" && (
                    <Select
                      label="Колода"
                      value={deckId}
                      onChange={(value) => {
                        setDeckId(value);
                        const nextDeck = availableDecks.find(
                          (deck) => deck.deck_id === value,
                        );
                        const options = uniqueTopics(nextDeck?.topics ?? []);
                        setCategory(
                          existingTopic(options, category) ?? options[0] ?? "",
                        );
                      }}
                      disabled={availableDecks.length === 0}
                      data={availableDecks.map((deck) => ({
                        value: deck.deck_id,
                        label: deck.deck_title,
                      }))}
                    />
                  )}
                  <Select
                    label="1. Широкая тема"
                    description="Карточка попадёт в одну из уже существующих групп для учеников."
                    placeholder="Выберите тему"
                    required
                    searchable
                    allowDeselect={false}
                    data={selectedDeckTopics}
                    value={selectedCreateTopic}
                    onChange={(value) => value && setCategory(value)}
                    nothingFoundMessage="В выбранной колоде пока нет тем"
                  />
                  {!selectedCreateTopic && availableDecks.length > 0 && (
                    <Alert color="yellow" title="AI не выбрал широкую тему">
                      Выберите подходящую существующую тему вручную. Платформа
                      больше не подставляет первую тему колоды автоматически.
                    </Alert>
                  )}
                  <TextInput
                    label="Детальная подтема (необязательно)"
                    description="Необязательно. Не влияет на широкую группировку карточек."
                    value={subcategory}
                    onChange={(event) =>
                      setSubcategory(event.currentTarget.value)
                    }
                  />
                  <Textarea
                    label="2. Формулировка вопроса"
                    minRows={3}
                    value={question}
                    onChange={(event) => setQuestion(event.currentTarget.value)}
                  />
                  <Textarea
                    label="3. Ответ карточки"
                    minRows={8}
                    value={answer}
                    onChange={(event) => setAnswer(event.currentTarget.value)}
                  />
                  {!answer.trim() && (
                    <Alert color="yellow" title="AI-ответ ещё не сформирован">
                      <Stack align="flex-start" gap="sm">
                        <Text size="sm">
                          Запустите генерацию: при наличии материалов ответ
                          будет проверен по ним, иначе появится AI-черновик с
                          пометкой о необходимости ручной проверки.
                        </Text>
                        {scope === "admin" ? (
                          <Button
                            variant="light"
                            loading={generateAnswer.isPending}
                            disabled={mutation || answerGenerationRequested}
                            onClick={requestAnswerGeneration}
                          >
                            {answerGenerationRequested
                              ? "AI формирует ответ…"
                              : "Сгенерировать AI-ответ"}
                          </Button>
                        ) : (
                          <Text size="sm">
                            Заполните ответ вручную и сохраните исправления.
                          </Text>
                        )}
                      </Stack>
                    </Alert>
                  )}
                  {cluster.answer_status === "needs_expert_source" && (
                    <Alert color="red" title="Нужна экспертная проверка">
                      Во внутренней базе недостаточно подтверждающих материалов.
                      Проверьте ответ вручную перед созданием карточки.
                    </Alert>
                  )}
                </Stack>
              </Card>
            )}
            {(can("update_draft") ||
              (scope === "admin" &&
                (can("link_card") || can("create_card")))) && (
              <Card withBorder style={{ order: 3 }}>
                <Stack>
                  <div>
                    <Title order={3}>5. Примите решение</Title>
                    <Text size="sm" c="dimmed" mt={4}>
                      Если найден полный дубль — свяжите вопросы. Если карточка
                      новая — создайте её из проверенных полей выше.
                    </Text>
                  </div>
                  <Group>
                    {can("update_draft") && (
                      <Button
                        variant="light"
                        loading={updateDraft.isPending}
                        disabled={
                          mutation ||
                          !proposalChanged ||
                          !selectedCreateTopic ||
                          !question.trim()
                        }
                        onClick={saveProposalDraft}
                      >
                        Сохранить исправления
                      </Button>
                    )}
                    {can("link_card") && (
                      <Button
                        variant="light"
                        loading={link.isPending}
                        disabled={mutation || !selectedCardId}
                        onClick={linkCard}
                      >
                        Связать с выбранной карточкой
                      </Button>
                    )}
                    {can("create_card") && (
                      <Button
                        loading={create.isPending}
                        disabled={
                          mutation ||
                          !deckId ||
                          !selectedCreateTopic ||
                          !question.trim() ||
                          !answer.trim()
                        }
                        onClick={createCard}
                      >
                        Создать новую карточку
                      </Button>
                    )}
                  </Group>
                </Stack>
              </Card>
            )}
          </Stack>
        </Tabs.Panel>

        <Tabs.Panel value="history" pt="lg">
          <Stack>
            <Accordion variant="separated" multiple>
              {cluster.decisions.map((decision) => (
                <Accordion.Item key={decision.id} value={decision.id}>
                  <Accordion.Control>
                    {decisionTypeLabels[decision.decision_type]} ·{" "}
                    {formatDate(decision.created_at)}
                  </Accordion.Control>
                  <Accordion.Panel>
                    <Stack gap="xs">
                      <Text>{decision.reason}</Text>
                      <Text size="sm" c="dimmed">
                        Источник:{" "}
                        {decisionSourceLabels[decision.decision_source]} ·
                        confidence {percent(decision.confidence)}
                      </Text>
                      {decision.is_overridden && (
                        <Alert color="yellow" title="Решение отменено">
                          {decision.override_reason}
                        </Alert>
                      )}
                    </Stack>
                  </Accordion.Panel>
                </Accordion.Item>
              ))}
            </Accordion>
            {cluster.manual_history.map((event) => (
              <Card key={event.id} withBorder>
                <Text fw={700}>{event.action}</Text>
                <Text size="sm">
                  {event.actor_name ?? "Система"} ·{" "}
                  {formatDate(event.created_at)}
                </Text>
                {event.reason && <Text size="sm">{event.reason}</Text>}
              </Card>
            ))}
            {cluster.decisions.length === 0 &&
              cluster.manual_history.length === 0 && (
                <Card withBorder>
                  <Text c="dimmed">История пока пуста.</Text>
                </Card>
              )}
          </Stack>
        </Tabs.Panel>
      </Tabs>

      <Card withBorder>
        <Stack>
          <Title order={3}>Действия с кластером</Title>
          <Group>
            {can("mark_important") && (
              <Button
                variant="light"
                disabled={mutation}
                onClick={() =>
                  runStateAction("mark-important", "Пометить кластер важным")
                }
              >
                Пометить важным
              </Button>
            )}
            {can("defer") && (
              <Button
                variant="light"
                color="orange"
                disabled={mutation}
                onClick={() =>
                  runStateAction("defer", "Отложить до следующего появления")
                }
              >
                Отложить
              </Button>
            )}
            {can("ignore") && (
              <Button
                variant="light"
                color="gray"
                disabled={mutation}
                onClick={() =>
                  runStateAction("ignore", "Исключить из общей базы")
                }
              >
                Исключить из карточек
              </Button>
            )}
            {can("reopen") && (
              <Button
                variant="light"
                disabled={mutation}
                onClick={() =>
                  runStateAction("reopen", "Вернуть кластер в очередь")
                }
              >
                Вернуть в очередь
              </Button>
            )}
          </Group>
          {scope === "admin" && can("merge") && (
            <Card withBorder>
              <Stack>
                <Title order={3}>Объединить с другим кластером</Title>
                <Text size="sm" c="dimmed">
                  Укажите ID и текущую версию целевого кластера. Направления и
                  типы дополнительно проверит сервер.
                </Text>
                <Group grow align="flex-end">
                  <TextInput
                    label="ID целевого кластера"
                    value={mergeClusterId}
                    onChange={(event) =>
                      setMergeClusterId(event.currentTarget.value)
                    }
                  />
                  <NumberInput
                    label="Версия целевого кластера"
                    min={1}
                    value={mergeClusterVersion}
                    onChange={(value) =>
                      setMergeClusterVersion(
                        typeof value === "number" ? value : "",
                      )
                    }
                  />
                </Group>
                <Button
                  color="orange"
                  variant="light"
                  loading={merge.isPending}
                  disabled={
                    mutation ||
                    !mergeClusterId.trim() ||
                    typeof mergeClusterVersion !== "number"
                  }
                  onClick={mergeCluster}
                >
                  Объединить кластеры
                </Button>
              </Stack>
            </Card>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}

export function CardAutomationClusterDetailPage({
  scope,
}: {
  scope: CardAutomationScope;
}) {
  const { clusterId = "" } = useParams();
  const query = useQuestionCluster(clusterId, scope);
  if (query.isPending) return <LoadingState label="Загружаем кластер…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  return (
    <ClusterDetail
      key={`${query.data.id}:${query.data.version}`}
      cluster={query.data}
      reload={() => query.refetch()}
      scope={scope}
    />
  );
}

export function AdminCardAutomationClusterDetailPage() {
  return <CardAutomationClusterDetailPage scope="admin" />;
}
