import {
  Badge,
  Button,
  Card,
  Group,
  SegmentedControl,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useMe } from "../features/auth/queries";
import {
  useDeleteIntelligenceInterview,
  useMentorIntelligenceInterviews,
} from "../features/interviews/intelligenceQueries";

type QueueStatus = "needs_review" | "reviewed" | "processing" | "all";

export function MentorInterviewIntelligencePage() {
  const [status, setStatus] = useState<QueueStatus>("needs_review");
  const query = useMentorIntelligenceInterviews(status);
  const me = useMe();
  const remove = useDeleteIntelligenceInterview();
  if (query.isPending || me.isPending) return <LoadingState />;
  if (query.isError || me.isError)
    return <ErrorState retry={() => void query.refetch()} />;

  const deleteInterview = (id: string) => {
    if (
      window.confirm(
        "Удалить зависший AI-разбор, транскрипцию и загруженную запись?",
      )
    )
      remove.mutate(id);
  };

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Ментор · Interview Intelligence"
        title="Разборы учеников"
        description="Проверяйте AI-рекомендации, оставляйте комментарии и отслеживайте обработку записей."
      />
      <SegmentedControl
        value={status}
        onChange={(value) => setStatus(value as QueueStatus)}
        data={[
          { value: "needs_review", label: "Нужна проверка" },
          { value: "reviewed", label: "Проверено" },
          { value: "processing", label: "В обработке" },
          { value: "all", label: "Все" },
        ]}
      />
      {query.data.items.length === 0 ? (
        <Card withBorder>
          <Text c="dimmed">В этой очереди пока нет интервью.</Text>
        </Card>
      ) : (
        query.data.items.map((interview) => (
          <Card key={interview.id} withBorder>
            <Group justify="space-between" align="flex-start">
              <div>
                <Text className="technical-label">
                  {interview.student_name} · {interview.track_title}
                </Text>
                <Title order={3}>{interview.company_name}</Title>
                <Text c="dimmed">{interview.position_name}</Text>
              </div>
              <Stack align="flex-end" gap="xs">
                <Badge>{interview.processing_status}</Badge>
                <Text size="sm">{interview.question_count} вопросов</Text>
                <Group gap="xs">
                  {me.data.role === "admin" &&
                    !["ready", "failed"].includes(
                      interview.processing_status,
                    ) && (
                      <Button
                        color="red"
                        variant="light"
                        size="xs"
                        loading={remove.isPending}
                        onClick={() => deleteInterview(interview.id)}
                      >
                        Удалить зависший
                      </Button>
                    )}
                  <Button
                    component={Link}
                    to={`/mentor/interview-reviews/${interview.id}`}
                    size="xs"
                  >
                    Открыть разбор
                  </Button>
                </Group>
              </Stack>
            </Group>
          </Card>
        ))
      )}
    </Stack>
  );
}
