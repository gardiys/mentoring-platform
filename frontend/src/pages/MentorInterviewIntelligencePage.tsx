import {
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
  useDeleteIntelligenceInterview,
  useMentorIntelligenceInterviews,
} from "../features/interviews/intelligenceQueries";
import { intelligenceStatusLabels } from "../features/interviews/intelligencePresentation";
import type { IntelligenceInterviewSummary } from "../types/api";

type QueueStatus = "needs_review" | "reviewed" | "processing" | "all";

const queueStatusOptions = [
  { value: "needs_review", label: "Нужна проверка" },
  { value: "reviewed", label: "Проверено" },
  { value: "processing", label: "В обработке" },
  { value: "all", label: "Все" },
] satisfies { value: QueueStatus; label: string }[];

export function MentorInterviewIntelligencePage() {
  const [status, setStatus] = useState<QueueStatus>("needs_review");
  const [page, setPage] = useState(1);
  const query = useMentorIntelligenceInterviews(status, page);
  const me = useMe();
  const remove = useDeleteIntelligenceInterview();
  if (query.isPending || me.isPending) return <LoadingState />;
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
    setStatus(value as QueueStatus);
    setPage(1);
  };

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Ментор · Interview Intelligence"
        title="Разборы учеников"
        description="Проверяйте AI-рекомендации, оставляйте комментарии и отслеживайте обработку записей."
      />
      <Select
        hiddenFrom="sm"
        label="Статус очереди"
        value={status}
        onChange={changeStatus}
        data={queueStatusOptions}
      />
      <SegmentedControl
        visibleFrom="sm"
        fullWidth
        value={status}
        onChange={changeStatus}
        data={queueStatusOptions}
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
                </div>
                <Stack align="flex-end" gap="xs">
                  <Badge
                    color={
                      interview.processing_status === "failed"
                        ? "red"
                        : interview.processing_status === "ready"
                          ? "green"
                          : "blue"
                    }
                  >
                    {intelligenceStatusLabels[interview.processing_status]}
                  </Badge>
                  <Text size="sm">{interview.question_count} вопросов</Text>
                  <Group gap="xs">
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
              </Group>
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
