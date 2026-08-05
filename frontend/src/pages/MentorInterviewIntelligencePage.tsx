import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Pagination,
  SegmentedControl,
  Select,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router-dom";
import { notifications } from "@mantine/notifications";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useMe } from "../features/auth/queries";
import {
  useAdminIntelligenceOperations,
  useAdminRequeueIntelligenceInterview,
  useDeleteIntelligenceInterview,
  useMentorIntelligenceInterviews,
  useRetryIntelligenceInterview,
} from "../features/interviews/intelligenceQueries";
import { intelligenceStatusLabels } from "../features/interviews/intelligencePresentation";
import type { IntelligenceInterviewSummary } from "../types/api";

type QueueStatus =
  "requested" | "needs_review" | "reviewed" | "processing" | "all";

const queueStatusOptions = [
  { value: "requested", label: "Ждут запуска" },
  { value: "needs_review", label: "Нужна проверка" },
  { value: "reviewed", label: "Проверено" },
  { value: "processing", label: "В обработке" },
  { value: "all", label: "Все" },
] satisfies { value: QueueStatus; label: string }[];

export function MentorInterviewIntelligencePage() {
  const [selectedStatus, setSelectedStatus] = useState<QueueStatus | null>(
    null,
  );
  const [page, setPage] = useState(1);
  const me = useMe();
  const isAdmin = me.data?.role === "admin";
  const status = selectedStatus ?? (isAdmin ? "requested" : "needs_review");
  const query = useMentorIntelligenceInterviews(status, page, Boolean(me.data));
  const operations = useAdminIntelligenceOperations(isAdmin);
  const requeue = useAdminRequeueIntelligenceInterview();
  const retry = useRetryIntelligenceInterview();
  const remove = useDeleteIntelligenceInterview();
  if (me.isPending || (me.data && query.isPending)) return <LoadingState />;
  if (me.isError || query.isError)
    return (
      <ErrorState
        error={query.error ?? me.error}
        retry={() => {
          void query.refetch();
          void me.refetch();
        }}
      />
    );
  if (!query.data) return <LoadingState />;

  const deleteInterview = (interview: IntelligenceInterviewSummary) => {
    if (
      window.confirm(
        `Удалить AI-разбор со статусом «${intelligenceStatusLabels[interview.processing_status]}» и его транскрипцию? Исходная запись останется в треке, но повторно запустить разбор будет нельзя.`,
      )
    ) {
      remove.mutate(interview.id, {
        onSuccess: () => {
          if (query.data.items.length === 1 && page > 1) setPage(page - 1);
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      });
    }
  };

  const changeStatus = (value: string | null) => {
    if (!value) return;
    setSelectedStatus(value as QueueStatus);
    setPage(1);
  };

  const startProcessing = (interview: IntelligenceInterviewSummary) => {
    const mutation = interview.processing_status === "failed" ? retry : requeue;
    const action =
      interview.processing_status === "failed"
        ? "повторить обработку"
        : "поставить текущий этап в очередь";
    if (
      !window.confirm(
        `Запустить AI-разбор для ${interview.student_name} · ${interview.company_name}: ${action}?`,
      )
    )
      return;
    mutation.mutate(interview.id, {
      onSuccess: () =>
        notifications.show({
          color: "green",
          message:
            interview.processing_status === "failed"
              ? "Повторная обработка запущена"
              : "AI-разбор поставлен в очередь",
        }),
      onError: (error) =>
        notifications.show({ color: "red", message: error.message }),
    });
  };

  const visibleStatusOptions = isAdmin
    ? queueStatusOptions
    : queueStatusOptions.filter((option) => option.value !== "requested");
  const transcriptionWorkerStatus =
    operations.data?.workers?.transcription.status ?? "unknown";
  const openaiWorkerStatus =
    operations.data?.workers?.openai.status ?? "unknown";
  const workerProblem = operations.data
    ? !operations.data.queues.available ||
      transcriptionWorkerStatus !== "healthy" ||
      openaiWorkerStatus !== "healthy"
    : false;
  const queueUnavailable = operations.data?.queues.available === false;

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Ментор · Interview Intelligence"
        title="Разборы учеников"
        description="Проверяйте AI-рекомендации, оставляйте комментарии и отслеживайте обработку записей."
      />
      {isAdmin && operations.isError && (
        <Alert color="yellow" title="Не удалось проверить очередь AI-разборов">
          Список доступен, но состояние фоновых обработчиков сейчас неизвестно.
        </Alert>
      )}
      {isAdmin && operations.data && (
        <Card withBorder>
          <Stack gap="sm">
            <Group justify="space-between" align="flex-start">
              <div>
                <Text fw={700}>Состояние AI-обработки</Text>
                <Text size="sm" c="dimmed">
                  В очереди распознавания:{" "}
                  {operations.data.queues.transcription_depth ?? "—"}
                  {" · "}в очереди анализа:{" "}
                  {operations.data.queues.openai_depth ?? "—"}
                </Text>
              </div>
              <Badge color={workerProblem ? "red" : "green"}>
                {workerProblem ? "Требует внимания" : "Воркеры работают"}
              </Badge>
            </Group>
            {!operations.data.queues.available && (
              <Alert color="red" title="Redis и очереди недоступны">
                Кнопка запуска не сможет передать задачу в обработку, пока
                соединение с очередью не восстановится.
              </Alert>
            )}
            {operations.data.queues.available &&
              transcriptionWorkerStatus !== "healthy" && (
                <Alert color="red" title="Воркер распознавания не отвечает">
                  Новые записи останутся в статусе «Ожидает запуска обработки».
                  Проверьте контейнер intelligence-worker.
                </Alert>
              )}
            {operations.data.queues.available &&
              openaiWorkerStatus !== "healthy" && (
                <Alert color="yellow" title="Воркер AI-анализа не отвечает">
                  Расшифровка может завершиться, но разбор вопросов и ответов не
                  продолжится. Проверьте контейнер intelligence-ai-worker.
                </Alert>
              )}
          </Stack>
        </Card>
      )}
      <Select
        hiddenFrom="sm"
        label="Статус очереди"
        value={status}
        onChange={changeStatus}
        data={visibleStatusOptions}
      />
      <SegmentedControl
        aria-label="Статус очереди"
        visibleFrom="sm"
        fullWidth
        value={status}
        onChange={changeStatus}
        data={visibleStatusOptions}
      />
      {query.isFetching && !query.isPending && (
        <Text size="xs" c="dimmed" role="status">
          Обновляем очередь…
        </Text>
      )}
      {query.data.items.length === 0 ? (
        <Card withBorder>
          <Text c="dimmed">В этой очереди пока нет интервью.</Text>
        </Card>
      ) : (
        query.data.items.map((interview) => {
          const staleSince =
            Date.now() - new Date(interview.updated_at).getTime();
          const canDeleteFromQueue =
            me.data.role === "admin" &&
            (interview.processing_status === "failed" ||
              (!["ready", "awaiting_candidate_speaker"].includes(
                interview.processing_status,
              ) &&
                staleSince >= 60 * 60 * 1_000));
          return (
            <Card key={interview.id} withBorder>
              <Stack gap="md">
                <Group
                  justify="space-between"
                  align="flex-start"
                  className="responsive-card-header"
                >
                  <div className="min-width-zero">
                    <Text className="technical-label">
                      {interview.student_name} · {interview.track_title}
                    </Text>
                    <Title order={3}>{interview.company_name}</Title>
                    <Text c="dimmed">{interview.position_name}</Text>
                    <Text size="xs" c="dimmed" mt="xs">
                      Запрошен{" "}
                      {new Date(interview.created_at).toLocaleString("ru-RU")}
                    </Text>
                  </div>
                  <Stack align="flex-end" gap="xs">
                    <Badge
                      color={
                        interview.processing_status === "failed"
                          ? "red"
                          : interview.processing_status === "ready"
                            ? "green"
                            : interview.processing_status === "uploaded"
                              ? "yellow"
                              : "blue"
                      }
                    >
                      {intelligenceStatusLabels[interview.processing_status]}
                    </Badge>
                    <Text size="sm">{interview.question_count} вопросов</Text>
                  </Stack>
                </Group>

                {interview.processing_error_message && (
                  <Alert
                    color={
                      interview.processing_status === "failed"
                        ? "red"
                        : "yellow"
                    }
                    title={
                      interview.processing_status === "failed"
                        ? "Причина остановки"
                        : "Последняя ошибка обработки"
                    }
                  >
                    <Text size="sm">{interview.processing_error_message}</Text>
                    {interview.processing_error_code && (
                      <Text size="xs" c="dimmed" mt={4}>
                        Код: {interview.processing_error_code}
                      </Text>
                    )}
                  </Alert>
                )}
                {isAdmin &&
                  interview.processing_status === "uploaded" &&
                  !interview.processing_error_message && (
                    <Text size="sm" c="dimmed">
                      Файл принят, но воркер ещё не зафиксировал первую попытку
                      обработки. Задачу можно безопасно вернуть в очередь.
                    </Text>
                  )}

                <Group justify="flex-end" gap="xs">
                  {isAdmin &&
                    (interview.can_requeue_processing ||
                      interview.processing_status === "failed") && (
                      <Button
                        variant="light"
                        size="xs"
                        disabled={query.isPlaceholderData || queueUnavailable}
                        loading={
                          (requeue.isPending &&
                            requeue.variables === interview.id) ||
                          (retry.isPending && retry.variables === interview.id)
                        }
                        onClick={() => startProcessing(interview)}
                      >
                        {interview.processing_status === "uploaded"
                          ? "Запустить AI-разбор"
                          : interview.processing_status === "failed"
                            ? "Повторить обработку"
                            : "Вернуть этап в очередь"}
                      </Button>
                    )}
                  {canDeleteFromQueue && (
                    <Button
                      color="red"
                      variant="light"
                      size="xs"
                      disabled={query.isPlaceholderData}
                      loading={
                        remove.isPending && remove.variables === interview.id
                      }
                      onClick={() => deleteInterview(interview)}
                    >
                      Удалить разбор
                    </Button>
                  )}
                  <Button
                    component={Link}
                    to={`/mentor/interview-reviews/${interview.id}`}
                    size="xs"
                    disabled={query.isPlaceholderData}
                  >
                    Открыть разбор
                  </Button>
                </Group>
              </Stack>
            </Card>
          );
        })
      )}
      {query.data.total > query.data.limit && (
        <Pagination
          value={page}
          onChange={setPage}
          total={Math.ceil(query.data.total / query.data.limit)}
          disabled={query.isPlaceholderData}
          withEdges
          mx="auto"
        />
      )}
    </Stack>
  );
}
