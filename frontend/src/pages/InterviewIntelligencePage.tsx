import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Radio,
  Select,
  SimpleGrid,
  Stack,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { api } from "../api/endpoints";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useMe } from "../features/auth/queries";
import {
  useAddIntelligenceComment,
  useCompleteIntelligenceReview,
  useDeleteIntelligenceInterview,
  useGenerateIntelligenceOverview,
  useIntelligenceInterview,
  useIntelligenceQuestionModeration,
  useIntelligenceReviewAction,
  useRetryIntelligenceInterview,
  useSelectIntelligenceCandidate,
} from "../features/interviews/intelligenceQueries";
import type {
  IntelligenceAssessment,
  IntelligenceProcessingStatus,
  IntelligenceQuestion,
} from "../types/api";

const statusLabels: Record<IntelligenceProcessingStatus, string> = {
  draft: "Ожидает загрузки",
  uploaded: "Файл загружен",
  transcription_submitted: "Отправлено в распознавание",
  transcribing: "Распознаём речь",
  transcript_ready: "Расшифровка готова",
  awaiting_candidate_speaker: "Нужно выбрать кандидата",
  analyzing: "Анализируем ответы",
  ready: "Разбор готов",
  failed: "Ошибка обработки",
};

const assessmentLabels: Record<IntelligenceAssessment, string> = {
  correct: "Верно",
  mostly_correct: "В основном верно",
  partial: "Частично",
  mostly_incorrect: "В основном неверно",
  incorrect: "Неверно",
  unable_to_assess: "Недостаточно данных",
};

const questionKindLabels = {
  technical: "Технический",
  hr: "HR",
  organizational: "Организационный",
  other: "Иное",
} as const;

function timestamp(milliseconds: number | null) {
  if (milliseconds === null) return "—";
  const seconds = Math.floor(milliseconds / 1_000);
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, "0")}`;
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
  const [questionText, setQuestionText] = useState(question.question_text);
  const [answerText, setAnswerText] = useState(
    review?.suggested_better_answer || question.answer?.answer_text || "",
  );
  const [category, setCategory] = useState(question.category);
  const [frequency, setFrequency] = useState<"frequent" | "occasional">(
    "occasional",
  );
  const canReview = reviewerRole !== "student";
  const moderate = (
    action: "recommend" | "approve" | "reject",
    includeCard = false,
  ) =>
    moderationMutation.mutate(
      {
        interviewId,
        questionId: question.id,
        payload: {
          action,
          ...(includeCard
            ? {
                question_markdown: questionText.trim(),
                answer_markdown: answerText.trim(),
                category: category.trim(),
                frequency,
              }
            : {}),
        },
      },
      {
        onSuccess: () =>
          notifications.show({
            color: "green",
            message:
              action === "approve"
                ? "Вопрос добавлен в карточки"
                : action === "recommend"
                  ? "Вопрос рекомендован администратору"
                  : "Вопрос отклонён",
          }),
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
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
            <Badge color={question.question_kind === "technical" ? "blue" : "gray"}>
              {questionKindLabels[question.question_kind]}
            </Badge>
            <Badge variant="outline">{question.difficulty}</Badge>
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
                        reviewMutation.mutate({
                          interviewId,
                          reviewId: review.id,
                          action: "approve",
                        })
                      }
                    >
                      Подтвердить
                    </Button>
                    <Button
                      size="xs"
                      color="gray"
                      variant="light"
                      loading={reviewMutation.isPending}
                      onClick={() =>
                        reviewMutation.mutate({
                          interviewId,
                          reviewId: review.id,
                          action: "reject",
                        })
                      }
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
                  <>
                    <Textarea
                      label="Вопрос"
                      minRows={2}
                      value={questionText}
                      onChange={(event) =>
                        setQuestionText(event.currentTarget.value)
                      }
                    />
                    <Textarea
                      label="Проверенный ответ для обратной стороны карточки"
                      minRows={4}
                      required
                      value={answerText}
                      onChange={(event) =>
                        setAnswerText(event.currentTarget.value)
                      }
                    />
                    <Group grow align="flex-end">
                      <TextInput
                        label="Тема"
                        value={category}
                        onChange={(event) =>
                          setCategory(event.currentTarget.value)
                        }
                      />
                      <Select
                        label="Частота"
                        data={[
                          { value: "frequent", label: "Частый вопрос" },
                          { value: "occasional", label: "Нечастый вопрос" },
                        ]}
                        value={frequency}
                        onChange={(value) =>
                          setFrequency(
                            value === "frequent" ? "frequent" : "occasional",
                          )
                        }
                      />
                    </Group>
                    <Group>
                      <Button
                        size="xs"
                        loading={moderationMutation.isPending}
                        disabled={
                          !questionText.trim() ||
                          !answerText.trim() ||
                          !category.trim()
                        }
                        onClick={() => moderate("approve", true)}
                      >
                        Добавить в карточки
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
                  </>
                )}
              {reviewerRole === "mentor" &&
                question.moderation_status !== "approved" && (
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
  const mediaRef = useRef<HTMLMediaElement>(null);

  if (query.isPending || me.isPending)
    return <LoadingState label="Загружаем разбор…" />;
  if (query.isError || me.isError)
    return <ErrorState retry={() => void query.refetch()} />;
  const interview = query.data;
  const canReview = me.data.role === "mentor" || me.data.role === "admin";
  const canDelete =
    me.data.role === "admin" || interview.student_id === me.data.id;
  const hasUnmoderatedQuestions = interview.questions.some((question) =>
    ["pending", "mentor_approved"].includes(question.moderation_status),
  );

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
    });
  };

  const openMedia = async () => {
    try {
      setMedia(await api.intelligenceMedia(interview.id));
    } catch (error) {
      notifications.show({
        color: "red",
        message:
          error instanceof Error ? error.message : "Не удалось открыть запись",
      });
    }
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
            {statusLabels[interview.processing_status]}
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
              onClick={() => retry.mutate(interview.id)}
            >
              Повторить этап
            </Button>
          </Stack>
        </Alert>
      )}

      {interview.media_filename && (
        <Card withBorder>
          <Stack>
            <Group justify="space-between">
              <div>
                <Title order={3}>Запись</Title>
                <Text size="sm" c="dimmed">
                  {interview.media_filename}
                </Text>
              </div>
              {!media && (
                <Button variant="light" onClick={() => void openMedia()}>
                  Открыть запись
                </Button>
              )}
            </Group>
            {media?.content_type.startsWith("video/") && (
              <video
                ref={mediaRef as React.RefObject<HTMLVideoElement>}
                controls
                controlsList="nodownload noremoteplayback"
                src={media.url}
                style={{ width: "100%", maxHeight: 640, borderRadius: 12 }}
              />
            )}
            {media?.content_type.startsWith("audio/") && (
              <audio
                ref={mediaRef}
                controls
                controlsList="nodownload noremoteplayback"
                src={media.url}
                style={{ width: "100%" }}
              />
            )}
          </Stack>
        </Card>
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
                selectCandidate.mutate({
                  interviewId: interview.id,
                  speakerId: candidateId,
                })
              }
            >
              Продолжить анализ
            </Button>
          </Stack>
        </Card>
      )}

      {interview.transcript.length > 0 && (
        <Card withBorder>
          <Stack>
            <Title order={2}>Расшифровка</Title>
            {interview.transcript.map((item) => (
              <button
                key={item.id}
                type="button"
                className="transcript-line"
                onClick={() => {
                  if (mediaRef.current) {
                    mediaRef.current.currentTime = item.start_ms / 1_000;
                    void mediaRef.current.play();
                  }
                }}
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
        </Card>
      )}

      {interview.overview && (
        <Card withBorder>
          <Stack gap="md">
            <div>
              <Text className="technical-label">Итог AI-разбора</Text>
              <Title order={2}>Общее резюме</Title>
            </div>
            <Text style={{ whiteSpace: "pre-wrap" }}>
              {interview.overview.overall_summary}
            </Text>
            {interview.overview.key_topics.length > 0 && (
              <Group gap="xs">
                {interview.overview.key_topics.map((topic) => (
                  <Badge key={topic} variant="light">
                    {topic}
                  </Badge>
                ))}
              </Group>
            )}

            <Group justify="space-between" align="flex-start">
              <div>
                <Title order={3}>Коммуникация и soft skills</Title>
                <Text c="dimmed">
                  Оценка основана только на наблюдаемом тексте разговора.
                </Text>
              </div>
              {interview.overview.communication_score !== null && (
                <Badge size="lg">
                  {Math.round(interview.overview.communication_score * 100)}%
                </Badge>
              )}
            </Group>
            <Text>{interview.overview.communication_summary}</Text>

            {interview.overview.communication_dimensions.length > 0 && (
              <SimpleGrid cols={{ base: 1, md: 2 }}>
                {interview.overview.communication_dimensions.map(
                  (dimension) => (
                    <Card key={dimension.name} withBorder padding="sm">
                      <Group justify="space-between">
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
                    </Card>
                  ),
                )}
              </SimpleGrid>
            )}

            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <div>
                <Text fw={700}>Сильные стороны коммуникации</Text>
                {interview.overview.communication_strengths.length > 0 ? (
                  interview.overview.communication_strengths.map((item) => (
                    <Text key={item} size="sm">
                      • {item}
                    </Text>
                  ))
                ) : (
                  <Text size="sm" c="dimmed">
                    Недостаточно данных
                  </Text>
                )}
              </div>
              <div>
                <Text fw={700}>Что можно улучшить</Text>
                {interview.overview.communication_growth_areas.length > 0 ? (
                  interview.overview.communication_growth_areas.map((item) => (
                    <Text key={item} size="sm">
                      • {item}
                    </Text>
                  ))
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
        </Card>
      )}

      {canReview &&
        interview.processing_status === "ready" &&
        !interview.overview && (
          <Alert color="blue" title="Для этого разбора ещё нет общего резюме">
            <Stack gap="sm">
              <Text>
                Это мог быть разбор, созданный до добавления оценки коммуникации.
                Запустите формирование вручную — транскрипция повторно отправится
                в сервис анализа.
              </Text>
              <Button
                w="fit-content"
                variant="light"
                loading={generateOverview.isPending}
                onClick={() => generateOverview.mutate(interview.id)}
              >
                Сформировать резюме и soft skills
              </Button>
            </Stack>
          </Alert>
        )}

      {interview.questions.length > 0 && (
        <Stack>
          <Title order={2}>Вопросы и ответы</Title>
          {interview.questions.map((question) => (
            <QuestionCard
              key={question.id}
              question={question}
              reviewerRole={me.data.role}
              interviewId={interview.id}
            />
          ))}
        </Stack>
      )}

      {interview.mentor_comments.length > 0 && (
        <Stack>
          <Title order={2}>Фидбек ментора</Title>
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
                    disabled={
                      interview.suggested_review_count > 0 ||
                      hasUnmoderatedQuestions
                    }
                    onClick={() => completeReview.mutate(interview.id)}
                  >
                    Завершить проверку
                  </Button>
                )}
            </Group>
            {!interview.reviewed_at &&
              interview.suggested_review_count > 0 && (
                <Text size="sm" c="orange">
                  Сначала подтвердите или отклоните все AI-рекомендации.
                </Text>
              )}
            {!interview.reviewed_at && hasUnmoderatedQuestions && (
              <Text size="sm" c="orange">
                Сначала утвердите или отклоните все вопросы для общей базы.
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
                  { onSuccess: () => setComment("") },
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
