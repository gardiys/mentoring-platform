import {
  Accordion,
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Progress,
  Radio,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { type ReactNode, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/endpoints";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useMe } from "../features/auth/queries";
import {
  useAddIntelligenceComment,
  useAdminIntelligenceOperations,
  useAdminRequeueIntelligenceInterview,
  useCompleteIntelligenceReview,
  useDeleteIntelligenceInterview,
  useGenerateIntelligenceOverview,
  useIntelligenceInterview,
  useIntelligenceQuestionModeration,
  useIntelligenceReviewAction,
  useRetryIntelligenceInterview,
  useSelectIntelligenceCandidate,
} from "../features/interviews/intelligenceQueries";
import {
  intelligenceDifficultyLabels,
  intelligenceQuestionKindLabels,
  intelligenceStatusLabels,
} from "../features/interviews/intelligencePresentation";
import type {
  IntelligenceAssessment,
  IntelligenceInterviewOverview,
  IntelligenceQuestion,
} from "../types/api";
import { mediaKind } from "../utils/media";

const assessmentLabels: Record<IntelligenceAssessment, string> = {
  correct: "Верно",
  mostly_correct: "В основном верно",
  partial: "Частично",
  mostly_incorrect: "В основном неверно",
  incorrect: "Неверно",
  unable_to_assess: "Недостаточно данных",
};

function notifyMutationError(error: Error) {
  notifications.show({ color: "red", message: error.message });
}

function timestamp(milliseconds: number | null) {
  if (milliseconds === null) return "—";
  const seconds = Math.floor(milliseconds / 1_000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
}

function scorePercent(score: number | null) {
  return score === null ? null : Math.round(score * 100);
}

function scorePresentation(score: number | null) {
  if (score === null) {
    return { color: "gray", label: "Недостаточно данных" };
  }
  if (score >= 0.8) return { color: "green", label: "Сильный результат" };
  if (score >= 0.6) return { color: "blue", label: "Хорошая база" };
  if (score >= 0.4) return { color: "yellow", label: "Есть пробелы" };
  return { color: "orange", label: "Нужна проработка" };
}

function OverviewSummary({
  overview,
}: {
  overview: IntelligenceInterviewOverview;
}) {
  const technicalScore = overview.technical_score ?? null;
  const technical = scorePresentation(technicalScore);
  const technicalPercent = scorePercent(technicalScore);
  const communicationPercent = scorePercent(overview.communication_score);
  const priorityActions = (overview.priority_actions ?? []).slice(0, 6);

  return (
    <Card withBorder className="analysis-verdict-card">
      <Stack gap="lg">
        <Group justify="space-between" align="flex-start" wrap="wrap" gap="md">
          <div className="analysis-verdict-copy">
            <Text className="technical-label">Итог AI-разбора</Text>
            <Title order={2}>Вердикт</Title>
          </div>
          <Badge
            color={technical.color}
            variant="light"
            size="lg"
            className="analysis-verdict-badge"
          >
            {technical.label}
            {technicalPercent !== null ? ` · ${technicalPercent}%` : ""}
          </Badge>
        </Group>

        <Text className="analysis-overall-summary">
          {overview.overall_summary}
        </Text>

        <div className="analysis-score-strip">
          <div className="analysis-score-item">
            <Text className="technical-label">Техническая оценка</Text>
            <Text fw={800} size="xl">
              {technicalPercent === null ? "—" : `${technicalPercent}%`}
            </Text>
          </div>
          <div className="analysis-score-item">
            <Text className="technical-label">Коммуникация</Text>
            <Text fw={800} size="xl">
              {communicationPercent === null ? "—" : `${communicationPercent}%`}
            </Text>
          </div>
        </div>

        {priorityActions.length > 0 && (
          <section aria-labelledby="analysis-priority-actions-title">
            <Group justify="space-between" align="baseline" mb="sm">
              <Title order={3} id="analysis-priority-actions-title">
                Приоритетные улучшения
              </Title>
              <Text size="sm" c="dimmed">
                Приоритетов: {priorityActions.length}
              </Text>
            </Group>
            <SimpleGrid
              cols={{ base: 1, md: 2, xl: 3 }}
              spacing="sm"
            >
              {priorityActions.map((action, index) => (
                <div
                  key={`${action.title}-${index}`}
                  className="analysis-priority-action"
                >
                  <Group gap="sm" wrap="nowrap" align="flex-start">
                    <span className="analysis-priority-number">
                      {index + 1}
                    </span>
                    <div className="min-width-zero">
                      <Text fw={800}>{action.title}</Text>
                      <Text size="sm" c="dimmed" mt={4}>
                        {action.reason}
                      </Text>
                    </div>
                  </Group>
                  {action.steps.length > 0 && (
                    <ol className="analysis-action-steps">
                      {action.steps.map((step) => (
                        <li key={step}>{step}</li>
                      ))}
                    </ol>
                  )}
                  {action.success_criterion && (
                    <Text size="xs" className="analysis-success-criterion">
                      <b>Готово, когда:</b> {action.success_criterion}
                    </Text>
                  )}
                </div>
              ))}
            </SimpleGrid>
          </section>
        )}

        <Text size="xs" c="dimmed">
          Это учебная AI-оценка качества ответов, а не решение о найме.
        </Text>
      </Stack>
    </Card>
  );
}

function TechnicalTopics({
  overview,
  questions,
  onQuestionNavigate,
}: {
  overview: IntelligenceInterviewOverview;
  questions: IntelligenceQuestion[];
  onQuestionNavigate: (questionId: string) => void;
}) {
  const technicalScore = overview.technical_score ?? null;
  const technicalPercent = scorePercent(technicalScore);

  return (
    <Card withBorder className="analysis-technical-card">
      <Stack gap="md">
        <Group justify="space-between" align="flex-start" wrap="wrap">
          <div>
            <Text className="technical-label">Знания и точность ответов</Text>
            <Title order={2}>Техническая оценка по темам</Title>
          </div>
          <Badge
            color={scorePresentation(technicalScore).color}
            variant="light"
            size="lg"
          >
            {technicalPercent === null
              ? "Без общей оценки"
              : `Общая оценка · ${technicalPercent}%`}
          </Badge>
        </Group>

        {overview.technical_summary && (
          <Text c="dimmed">{overview.technical_summary}</Text>
        )}

        {overview.key_topics.length > 0 && (
          <Group gap="xs">
            {overview.key_topics.map((topic) => (
              <Badge key={topic} variant="light">
                {topic}
              </Badge>
            ))}
          </Group>
        )}

        {(overview.technical_topics ?? []).length > 0 ? (
          <Accordion
            multiple
            variant="separated"
            radius="md"
            chevronPosition="right"
            className="brand-accordion analysis-topic-accordion"
          >
            {(overview.technical_topics ?? []).map((topic, index) => {
              const percent = scorePercent(topic.score);
              const presentation = scorePresentation(topic.score);
              return (
                <Accordion.Item
                  key={`${topic.topic}-${index}`}
                  value={`${index}-${topic.topic}`}
                >
                  <Accordion.Control>
                    <div className="analysis-topic-control">
                      <Group
                        justify="space-between"
                        align="center"
                        wrap="nowrap"
                        gap="sm"
                      >
                        <div className="min-width-zero">
                          <Text fw={800} className="analysis-topic-name">
                            {topic.topic}
                          </Text>
                          <Text size="xs" c="dimmed">
                            {topic.questions_count} вопросов
                          </Text>
                        </div>
                        <Badge
                          color={presentation.color}
                          variant="light"
                          className="analysis-topic-score"
                        >
                          {percent === null ? "Нет оценки" : `${percent}%`}
                        </Badge>
                      </Group>
                      {percent !== null && (
                        <Progress
                          value={percent}
                          color={presentation.color}
                          size="sm"
                          radius="xl"
                          mt="xs"
                          aria-label={`Оценка темы ${topic.topic}: ${percent}%`}
                        />
                      )}
                    </div>
                  </Accordion.Control>
                  <Accordion.Panel>
                    <Stack gap="sm">
                      <Text size="sm">{topic.summary}</Text>
                      {(topic.strengths.length > 0 ||
                        topic.gaps.length > 0) && (
                        <SimpleGrid cols={{ base: 1, sm: 2 }} spacing="sm">
                          {topic.strengths.length > 0 && (
                            <div className="analysis-topic-points is-strength">
                              <Text fw={700} size="sm">
                                Что получилось
                              </Text>
                              <ul>
                                {topic.strengths.map((strength) => (
                                  <li key={strength}>{strength}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                          {topic.gaps.length > 0 && (
                            <div className="analysis-topic-points is-gap">
                              <Text fw={700} size="sm">
                                Что подтянуть
                              </Text>
                              <ul>
                                {topic.gaps.map((gap) => (
                                  <li key={gap}>{gap}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </SimpleGrid>
                      )}
                      {topic.next_step && (
                        <div className="analysis-topic-next-step">
                          <Text className="technical-label">Следующий шаг</Text>
                          <Text size="sm">{topic.next_step}</Text>
                        </div>
                      )}
                      {topic.evidence_question_numbers.length > 0 && (
                        <Group gap="xs">
                          <Text size="xs" c="dimmed">
                            Основано на вопросах:
                          </Text>
                          {topic.evidence_question_numbers.map((number) => {
                            const question = questions.find(
                              (item) => item.sequence_number === number,
                            );
                            if (!question) {
                              return (
                                <Badge key={number} size="sm" variant="outline">
                                  №{number}
                                </Badge>
                              );
                            }
                            return (
                              <a
                                key={number}
                                href={`#question-${question.id}`}
                                className="analysis-evidence-link"
                                aria-label={`Открыть вопрос №${number}`}
                                onClick={() => onQuestionNavigate(question.id)}
                              >
                                №{number}
                              </a>
                            );
                          })}
                        </Group>
                      )}
                    </Stack>
                  </Accordion.Panel>
                </Accordion.Item>
              );
            })}
          </Accordion>
        ) : (
          <Text size="sm" c="dimmed">
            По этой записи пока недостаточно данных для оценки отдельных тем.
          </Text>
        )}
      </Stack>
    </Card>
  );
}

function AnalysisSection({
  title,
  eyebrow,
  summary,
  defaultOpened = false,
  opened,
  onOpenedChange,
  children,
}: {
  title: string;
  eyebrow?: string;
  summary?: string;
  defaultOpened?: boolean;
  opened?: boolean;
  onOpenedChange?: (opened: boolean) => void;
  children: ReactNode;
}) {
  return (
    <Accordion
      variant="separated"
      radius="md"
      chevronPosition="right"
      className="brand-accordion analysis-accordion"
      defaultValue={opened === undefined && defaultOpened ? "content" : null}
      value={opened === undefined ? undefined : opened ? "content" : null}
      onChange={(value) => onOpenedChange?.(value === "content")}
    >
      <Accordion.Item value="content">
        <Accordion.Control>
          <Group
            justify="space-between"
            align="center"
            wrap="wrap"
            gap="xs"
            className="analysis-section-heading"
          >
            <div className="analysis-section-heading-copy">
              {eyebrow && <Text className="technical-label">{eyebrow}</Text>}
              <Title order={2} className="analysis-section-title">
                {title}
              </Title>
            </div>
            {summary && (
              <Badge
                variant="light"
                size="lg"
                className="analysis-section-summary"
              >
                {summary}
              </Badge>
            )}
          </Group>
        </Accordion.Control>
        <Accordion.Panel>{children}</Accordion.Panel>
      </Accordion.Item>
    </Accordion>
  );
}

function QuestionCard({
  question,
  reviewerRole,
  interviewId,
}: {
  question: IntelligenceQuestion;
  reviewerRole: "student" | "mentor" | "admin";
  interviewId: string;
}) {
  const reviewMutation = useIntelligenceReviewAction();
  const moderationMutation = useIntelligenceQuestionModeration();
  const review = question.answer?.reviews.at(-1);
  const canReview = reviewerRole !== "student";
  const moderate = (action: "recommend" | "reject") => {
    if (
      action === "reject" &&
      !window.confirm("Отклонить добавление этого вопроса в общую базу?")
    )
      return;
    moderationMutation.mutate(
      {
        interviewId,
        questionId: question.id,
        payload: { action },
      },
      {
        onSuccess: () =>
          notifications.show({
            color: "green",
            message:
              action === "recommend"
                ? "Вопрос рекомендован администратору"
                : "Вопрос отклонён",
          }),
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };
  return (
    <Card withBorder id={`question-${question.id}`}>
      <Stack>
        <Group justify="space-between" align="flex-start">
          <div>
            <Text className="technical-label">
              {timestamp(question.question_start_ms)} · {question.category}
            </Text>
            <Title order={3}>{question.question_text}</Title>
          </div>
          <Group gap="xs">
            <Badge
              color={question.question_kind === "technical" ? "blue" : "gray"}
            >
              {intelligenceQuestionKindLabels[question.question_kind]}
            </Badge>
            <Badge variant="outline">
              {intelligenceDifficultyLabels[question.difficulty]}
            </Badge>
            {question.is_low_confidence && (
              <Badge color="yellow">Проверьте текст</Badge>
            )}
          </Group>
        </Group>
        <div>
          <Text fw={700}>Ответ кандидата</Text>
          <Text style={{ whiteSpace: "pre-wrap" }}>
            {question.answer?.answer_text || "Ответ не найден"}
          </Text>
        </div>
        {review && (
          <Card withBorder bg="var(--mantine-color-default-hover)">
            <Stack gap="xs">
              <Group justify="space-between">
                <Badge color={review.status === "rejected" ? "gray" : "blue"}>
                  {assessmentLabels[review.assessment]}
                </Badge>
                {review.score !== null && (
                  <Text className="technical-label">
                    {Math.round(review.score * 100)}%
                  </Text>
                )}
              </Group>
              {review.summary && <Text>{review.summary}</Text>}
              {review.missing_points.length > 0 && (
                <Text size="sm" c="dimmed">
                  Что дополнить: {review.missing_points.map(String).join("; ")}
                </Text>
              )}
              {review.suggested_better_answer && (
                <Text size="sm">
                  <b>Улучшенный ответ:</b> {review.suggested_better_answer}
                </Text>
              )}
              {canReview &&
                review.source === "ai" &&
                review.status === "suggested" && (
                  <Group>
                    <Button
                      size="xs"
                      loading={reviewMutation.isPending}
                      onClick={() =>
                        reviewMutation.mutate(
                          {
                            interviewId,
                            reviewId: review.id,
                            action: "approve",
                          },
                          { onError: notifyMutationError },
                        )
                      }
                    >
                      Подтвердить
                    </Button>
                    <Button
                      size="xs"
                      color="gray"
                      variant="light"
                      loading={reviewMutation.isPending}
                      onClick={() => {
                        if (!window.confirm("Отклонить AI-рекомендацию?"))
                          return;
                        reviewMutation.mutate(
                          {
                            interviewId,
                            reviewId: review.id,
                            action: "reject",
                          },
                          { onError: notifyMutationError },
                        );
                      }}
                    >
                      Отклонить
                    </Button>
                  </Group>
                )}
            </Stack>
          </Card>
        )}
        {canReview && (
          <Card withBorder>
            <Stack gap="sm">
              <Group justify="space-between">
                <Text fw={700}>Добавление в общую базу вопросов</Text>
                <Badge
                  color={
                    question.moderation_status === "approved"
                      ? "green"
                      : question.moderation_status === "rejected"
                        ? "gray"
                        : "yellow"
                  }
                >
                  {question.moderation_status === "approved"
                    ? "Добавлен"
                    : question.moderation_status === "mentor_approved"
                      ? "Рекомендован ментором"
                      : question.moderation_status === "rejected"
                        ? "Отклонён"
                        : "Ожидает проверки"}
                </Badge>
              </Group>
              {reviewerRole === "admin" &&
                question.moderation_status !== "approved" && (
                  <Button
                    component={Link}
                    to={`/admin/interview-question-moderation/${question.id}`}
                    size="xs"
                    w="fit-content"
                    variant="light"
                  >
                    Открыть в очереди вопросов
                  </Button>
                )}
              {reviewerRole === "mentor" &&
                question.moderation_status === "pending" && (
                  <Group>
                    <Button
                      size="xs"
                      loading={moderationMutation.isPending}
                      onClick={() => moderate("recommend")}
                    >
                      Рекомендовать добавить
                    </Button>
                    <Button
                      size="xs"
                      color="gray"
                      variant="light"
                      loading={moderationMutation.isPending}
                      onClick={() => moderate("reject")}
                    >
                      Отклонить
                    </Button>
                  </Group>
                )}
            </Stack>
          </Card>
        )}
      </Stack>
    </Card>
  );
}

export function InterviewIntelligencePage() {
  const { interviewId = "" } = useParams();
  const navigate = useNavigate();
  const query = useIntelligenceInterview(interviewId);
  const me = useMe();
  const selectCandidate = useSelectIntelligenceCandidate();
  const retry = useRetryIntelligenceInterview();
  const requeue = useAdminRequeueIntelligenceInterview();
  const remove = useDeleteIntelligenceInterview();
  const addComment = useAddIntelligenceComment();
  const completeReview = useCompleteIntelligenceReview();
  const generateOverview = useGenerateIntelligenceOverview();
  const [candidateId, setCandidateId] = useState("");
  const [comment, setComment] = useState("");
  const [media, setMedia] = useState<{
    url: string;
    content_type: string;
  } | null>(null);
  const [isMediaLoading, setIsMediaLoading] = useState(false);
  const [pendingSeekMs, setPendingSeekMs] = useState<number | null>(null);
  const [questionsOpened, setQuestionsOpened] = useState(false);
  const mediaRef = useRef<HTMLMediaElement>(null);
  const operations = useAdminIntelligenceOperations(me.data?.role === "admin");
  const intelligenceMediaKind = media
    ? mediaKind(media.content_type, query.data?.media_filename)
    : null;

  useEffect(() => {
    const element = mediaRef.current;
    if (!element || pendingSeekMs === null) return;

    const seekAndPlay = () => {
      element.currentTime = pendingSeekMs / 1_000;
      void element.play().catch(() => undefined);
      setPendingSeekMs(null);
    };

    if (element.readyState >= 1) {
      seekAndPlay();
      return;
    }

    element.addEventListener("loadedmetadata", seekAndPlay, { once: true });
    return () => element.removeEventListener("loadedmetadata", seekAndPlay);
  }, [media, pendingSeekMs]);

  if (query.isPending || me.isPending)
    return <LoadingState label="Загружаем разбор…" />;
  if (query.isError || me.isError)
    return (
      <ErrorState
        error={query.error ?? me.error}
        retry={() => {
          void query.refetch();
          void me.refetch();
        }}
      />
    );
  const interview = query.data;
  const canReview = me.data.role === "mentor" || me.data.role === "admin";
  const canDelete =
    me.data.role !== "student" &&
    (me.data.role === "admin" || interview.student_id === me.data.id);

  const deleteInterview = () => {
    if (
      !window.confirm(
        "Удалить AI-разбор и транскрипцию? Исходная запись останется в треке. Повторно запустить разбор будет нельзя.",
      )
    )
      return;
    remove.mutate(interview.id, {
      onSuccess: () =>
        navigate(canReview ? "/mentor/interview-reviews" : "/interviews", {
          replace: true,
        }),
      onError: notifyMutationError,
    });
  };

  const openMedia = async () => {
    if (media) {
      setPendingSeekMs(null);
      setMedia(null);
      return;
    }
    setIsMediaLoading(true);
    try {
      setMedia(await api.intelligenceMedia(interview.id));
    } catch (error) {
      setPendingSeekMs(null);
      notifications.show({
        color: "red",
        message:
          error instanceof Error ? error.message : "Не удалось открыть запись",
      });
    } finally {
      setIsMediaLoading(false);
    }
  };

  const playFromTranscript = async (milliseconds: number) => {
    if (mediaRef.current) {
      mediaRef.current.currentTime = milliseconds / 1_000;
      await mediaRef.current.play().catch(() => undefined);
      return;
    }
    if (!interview.media_filename) return;
    setPendingSeekMs(milliseconds);
    await openMedia();
  };

  const revealQuestion = (questionId: string) => {
    setQuestionsOpened(true);
    window.setTimeout(() => {
      document.getElementById(`question-${questionId}`)?.scrollIntoView?.({
        behavior: "smooth",
        block: "center",
      });
    }, 0);
  };

  const handleMediaError = () => {
    setPendingSeekMs(null);
    setMedia(null);
    notifications.show({
      color: "yellow",
      message:
        "Не удалось воспроизвести запись. Откройте её снова, чтобы обновить ссылку.",
    });
  };

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow={`Interview Intelligence · ${interview.track_title}`}
        title={interview.company_name}
        description={interview.position_name ?? "Разбор записи собеседования"}
      />
      <SimpleGrid cols={{ base: 1, md: 3 }}>
        <Card withBorder>
          <Text className="technical-label">Статус</Text>
          <Badge
            mt="xs"
            color={interview.processing_status === "failed" ? "red" : "blue"}
          >
            {intelligenceStatusLabels[interview.processing_status]}
          </Badge>
        </Card>
        <Card withBorder>
          <Text className="technical-label">Вопросы</Text>
          <Title order={2}>{interview.question_count}</Title>
        </Card>
        <Card withBorder>
          <Text className="technical-label">Дата</Text>
          <Text fw={700}>
            {new Date(interview.interviewed_at).toLocaleString("ru-RU")}
          </Text>
        </Card>
      </SimpleGrid>

      {interview.processing_status === "failed" && (
        <Alert color="red" title="Обработка остановилась">
          <Stack gap="sm">
            <Text>
              {interview.processing.error_message ?? "Неизвестная ошибка"}
            </Text>
            <Button
              w="fit-content"
              loading={retry.isPending}
              onClick={() =>
                retry.mutate(interview.id, { onError: notifyMutationError })
              }
            >
              Повторить этап
            </Button>
          </Stack>
        </Alert>
      )}

      {interview.processing_status !== "failed" &&
        interview.processing_error_message && (
          <Alert color="yellow" title="Последняя ошибка обработки">
            <Text>{interview.processing_error_message}</Text>
            {interview.processing_error_code && (
              <Text size="xs" c="dimmed" mt={4}>
                Код: {interview.processing_error_code}
              </Text>
            )}
          </Alert>
        )}

      {me.data.role === "admin" && interview.can_requeue_processing && (
        <Alert
          color={interview.processing_status === "uploaded" ? "yellow" : "blue"}
          title={
            interview.processing_status === "uploaded"
              ? "Разбор ожидает запуска"
              : "Текущий этап можно вернуть в очередь"
          }
        >
          <Stack gap="sm">
            <Text>
              {interview.processing_status === "uploaded"
                ? "Файл уже загружен. Запустите обработку вручную, если задача не была подхвачена воркером."
                : "Используйте ручной запуск, если статус давно не меняется."}
            </Text>
            <Button
              w="fit-content"
              variant="light"
              disabled={operations.data?.queues.available === false}
              loading={requeue.isPending}
              onClick={() =>
                requeue.mutate(interview.id, {
                  onSuccess: () =>
                    notifications.show({
                      color: "green",
                      message: "Текущий этап AI-разбора поставлен в очередь",
                    }),
                  onError: notifyMutationError,
                })
              }
            >
              {interview.processing_status === "uploaded"
                ? "Запустить AI-разбор"
                : "Вернуть этап в очередь"}
            </Button>
          </Stack>
        </Alert>
      )}

      {interview.processing_status === "awaiting_candidate_speaker" && (
        <Card withBorder>
          <Stack>
            <div>
              <Title order={2}>Кто из спикеров — кандидат?</Title>
              <Text c="dimmed">
                Выберите себя по примерам реплик. После этого начнётся анализ
                ответов.
              </Text>
            </div>
            <Radio.Group value={candidateId} onChange={setCandidateId}>
              <Stack>
                {interview.speakers.map((speaker) => (
                  <Radio.Card
                    key={speaker.id}
                    value={speaker.id}
                    withBorder
                    p="md"
                    radius="md"
                  >
                    <Group wrap="nowrap" align="flex-start">
                      <Radio.Indicator />
                      <div>
                        <Text fw={700}>
                          Спикер {speaker.provider_speaker_key}
                        </Text>
                        {speaker.examples.slice(0, 3).map((item) => (
                          <Text key={item.id} size="sm" c="dimmed">
                            “{item.text}”
                          </Text>
                        ))}
                      </div>
                    </Group>
                  </Radio.Card>
                ))}
              </Stack>
            </Radio.Group>
            <Button
              disabled={!candidateId}
              loading={selectCandidate.isPending}
              onClick={() =>
                selectCandidate.mutate(
                  {
                    interviewId: interview.id,
                    speakerId: candidateId,
                  },
                  { onError: notifyMutationError },
                )
              }
            >
              Продолжить анализ
            </Button>
          </Stack>
        </Card>
      )}

      {interview.overview && (
        <>
          <OverviewSummary overview={interview.overview} />
          <TechnicalTopics
            overview={interview.overview}
            questions={interview.questions}
            onQuestionNavigate={revealQuestion}
          />
          <AnalysisSection
            eyebrow="Soft skills"
            title="Коммуникация и подача"
            summary={
              interview.overview.communication_score === null
                ? "Без оценки"
                : `${Math.round(interview.overview.communication_score * 100)}%`
            }
          >
            <Stack gap="md">
              <Text c="dimmed">
                Оценка основана только на наблюдаемом тексте разговора.
              </Text>
              <Text>{interview.overview.communication_summary}</Text>

              {interview.overview.communication_dimensions.length > 0 && (
                <SimpleGrid
                  cols={{ base: 1, md: 2 }}
                  className="analysis-communication-grid"
                >
                  {interview.overview.communication_dimensions.map(
                    (dimension) => (
                      <div
                        key={dimension.name}
                        className="analysis-communication-dimension"
                      >
                        <Group justify="space-between" wrap="nowrap">
                          <Text fw={700}>{dimension.name}</Text>
                          {dimension.score !== null && (
                            <Badge variant="outline">
                              {Math.round(dimension.score * 100)}%
                            </Badge>
                          )}
                        </Group>
                        <Text size="sm" mt="xs">
                          {dimension.summary}
                        </Text>
                      </div>
                    ),
                  )}
                </SimpleGrid>
              )}

              <SimpleGrid cols={{ base: 1, md: 2 }}>
                <div className="analysis-topic-points is-strength">
                  <Text fw={700}>Сильные стороны</Text>
                  {interview.overview.communication_strengths.length > 0 ? (
                    <ul>
                      {interview.overview.communication_strengths.map(
                        (item) => (
                          <li key={item}>{item}</li>
                        ),
                      )}
                    </ul>
                  ) : (
                    <Text size="sm" c="dimmed">
                      Недостаточно данных
                    </Text>
                  )}
                </div>
                <div className="analysis-topic-points is-gap">
                  <Text fw={700}>Что можно улучшить</Text>
                  {interview.overview.communication_growth_areas.length > 0 ? (
                    <ul>
                      {interview.overview.communication_growth_areas.map(
                        (item) => (
                          <li key={item}>{item}</li>
                        ),
                      )}
                    </ul>
                  ) : (
                    <Text size="sm" c="dimmed">
                      Недостаточно данных
                    </Text>
                  )}
                </div>
              </SimpleGrid>

              {interview.overview.caveats.length > 0 && (
                <Alert color="yellow" title="Ограничения оценки">
                  {interview.overview.caveats.join(" ")}
                </Alert>
              )}
            </Stack>
          </AnalysisSection>
        </>
      )}

      {canReview &&
        interview.processing_status === "ready" &&
        !interview.overview && (
          <Alert color="blue" title="Для этого разбора ещё нет общего резюме">
            <Stack gap="sm">
              <Text>
                Это мог быть разбор, созданный до добавления оценки
                коммуникации. Запустите формирование вручную — транскрипция
                повторно отправится в сервис анализа.
              </Text>
              <Button
                w="fit-content"
                variant="light"
                loading={generateOverview.isPending}
                onClick={() =>
                  generateOverview.mutate(interview.id, {
                    onError: notifyMutationError,
                  })
                }
              >
                Сформировать резюме и soft skills
              </Button>
            </Stack>
          </Alert>
        )}

      {interview.mentor_comments.length > 0 && (
        <AnalysisSection
          title="Фидбек ментора"
          summary={`Комментариев: ${interview.mentor_comments.length}`}
        >
          <Stack>
            {interview.mentor_comments.map((item) => (
              <Card
                key={item.id}
                withBorder
                style={{ borderColor: "var(--mantine-color-blue-6)" }}
              >
                <Text style={{ whiteSpace: "pre-wrap" }}>{item.text}</Text>
                <Text size="xs" c="dimmed" mt="xs">
                  {item.mentor_name}
                  {item.mentor_telegram_username
                    ? ` · @${item.mentor_telegram_username}`
                    : ""}
                </Text>
              </Card>
            ))}
          </Stack>
        </AnalysisSection>
      )}

      {interview.questions.length > 0 && (
        <AnalysisSection
          title="Вопросы и ответы"
          summary={`Вопросов: ${interview.questions.length}`}
          opened={questionsOpened}
          onOpenedChange={setQuestionsOpened}
        >
          <Stack>
            {interview.questions.map((question) => (
              <QuestionCard
                key={question.id}
                question={question}
                reviewerRole={me.data.role}
                interviewId={interview.id}
              />
            ))}
          </Stack>
        </AnalysisSection>
      )}

      {(interview.media_filename || interview.transcript.length > 0) && (
        <section
          className="analysis-materials"
          aria-labelledby="analysis-materials-title"
        >
          <div className="analysis-materials-heading">
            <Text className="technical-label">Материалы разбора</Text>
            <Title order={2} id="analysis-materials-title">
              Запись и расшифровка
            </Title>
            <Text c="dimmed" size="sm">
              Откройте запись или расшифровку, когда понадобится проверить
              конкретный вывод AI.
            </Text>
          </div>

          {interview.media_filename && (
            <Card withBorder className="analysis-media-card">
              <Stack>
                <Group
                  justify="space-between"
                  align="center"
                  className="responsive-card-header"
                >
                  <div className="min-width-zero">
                    <Title order={3}>Запись собеседования</Title>
                    <Text
                      size="sm"
                      c="dimmed"
                      className="analysis-media-filename"
                    >
                      {interview.media_filename}
                    </Text>
                  </div>
                  <Button
                    variant="light"
                    loading={isMediaLoading}
                    onClick={() => void openMedia()}
                  >
                    {media ? "Скрыть запись" : "Открыть запись"}
                  </Button>
                </Group>
                {media && intelligenceMediaKind === "video" && (
                  <video
                    ref={mediaRef as React.RefObject<HTMLVideoElement>}
                    controls
                    controlsList="nodownload noremoteplayback"
                    playsInline
                    preload="metadata"
                    src={media.url}
                    onError={handleMediaError}
                    className="analysis-media-player"
                  />
                )}
                {media && intelligenceMediaKind === "audio" && (
                  <audio
                    ref={mediaRef}
                    controls
                    controlsList="nodownload noremoteplayback"
                    preload="metadata"
                    src={media.url}
                    onError={handleMediaError}
                    className="analysis-audio-player"
                  />
                )}
                {media && !intelligenceMediaKind && (
                  <Alert color="yellow" title="Формат записи не распознан">
                    Не удалось определить, это аудио или видео. Проверьте имя и
                    формат исходного файла.
                  </Alert>
                )}
              </Stack>
            </Card>
          )}

          {interview.transcript.length > 0 && (
            <AnalysisSection
              title="Расшифровка"
              summary={`Реплик: ${interview.transcript.length}`}
            >
              <Stack gap="xs">
                {interview.media_filename && (
                  <Text size="sm" c="dimmed">
                    Нажмите на реплику — запись откроется на нужном месте.
                  </Text>
                )}
                <Stack gap={0}>
                  {interview.transcript.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      className="transcript-line"
                      disabled={!interview.media_filename}
                      title={
                        interview.media_filename
                          ? "Открыть запись на этом месте"
                          : "Для этой расшифровки запись недоступна"
                      }
                      onClick={() => void playFromTranscript(item.start_ms)}
                    >
                      <span>{timestamp(item.start_ms)}</span>
                      <b>
                        {item.speaker_role === "candidate"
                          ? "Кандидат"
                          : `Спикер ${item.speaker_key}`}
                      </b>
                      <span>{item.text}</span>
                    </button>
                  ))}
                </Stack>
              </Stack>
            </AnalysisSection>
          )}
        </section>
      )}

      {canReview && (
        <Card withBorder>
          <Stack>
            <Group justify="space-between" align="flex-start">
              <div>
                <Text fw={700}>Статус проверки</Text>
                <Text size="sm" c="dimmed">
                  {interview.reviewed_at
                    ? `Проверено ${new Date(interview.reviewed_at).toLocaleString("ru-RU")}`
                    : "Проверка ещё не завершена"}
                </Text>
              </div>
              {!interview.reviewed_at &&
                interview.processing_status === "ready" && (
                  <Button
                    variant="light"
                    loading={completeReview.isPending}
                    disabled={interview.suggested_review_count > 0}
                    onClick={() =>
                      completeReview.mutate(interview.id, {
                        onError: notifyMutationError,
                      })
                    }
                  >
                    Завершить проверку
                  </Button>
                )}
            </Group>
            {!interview.reviewed_at && interview.suggested_review_count > 0 && (
              <Text size="sm" c="orange">
                Сначала подтвердите или отклоните все AI-рекомендации.
              </Text>
            )}
            <Textarea
              label="Общий комментарий ученику"
              value={comment}
              onChange={(event) => setComment(event.currentTarget.value)}
              minRows={3}
            />
            <Button
              disabled={!comment.trim()}
              loading={addComment.isPending}
              onClick={() =>
                addComment.mutate(
                  { interviewId: interview.id, text: comment.trim() },
                  {
                    onSuccess: () => setComment(""),
                    onError: notifyMutationError,
                  },
                )
              }
            >
              Добавить комментарий
            </Button>
          </Stack>
        </Card>
      )}

      {canDelete && (
        <Card withBorder style={{ borderColor: "var(--mantine-color-red-6)" }}>
          <Group justify="space-between" align="center">
            <div>
              <Text fw={700}>Удаление AI-разбора</Text>
              <Text size="sm" c="dimmed">
                Можно удалить зависший или ошибочный AI-разбор. Запись и этап
                собеседования останутся в дневнике.
              </Text>
            </div>
            <Button
              color="red"
              variant="light"
              loading={remove.isPending}
              onClick={deleteInterview}
            >
              Удалить разбор
            </Button>
          </Group>
        </Card>
      )}

      <Button
        component={Link}
        to={canReview ? "/mentor/interview-reviews" : "/interviews"}
        variant="subtle"
        w="fit-content"
      >
        ← Назад к списку
      </Button>
    </Stack>
  );
}
