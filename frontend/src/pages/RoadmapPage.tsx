import {
  Accordion,
  Alert,
  Anchor,
  Badge,
  Button,
  Group,
  Paper,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { ProgressBar } from "../components/ProgressBar";
import { PageHeader } from "../components/PageHeader";
import { TopicStatusBadge } from "../components/TopicStatusBadge";
import { useRoadmap, useStartRoadmap } from "../features/roadmaps/queries";
import { formatDays } from "../utils/formatDays";

const dateFormatter = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "long",
  year: "numeric",
});

function formatDate(value: string) {
  return dateFormatter.format(new Date(value));
}

function currentLocalDate() {
  const now = new Date();
  return new Date(now.getTime() - now.getTimezoneOffset() * 60_000)
    .toISOString()
    .slice(0, 10);
}

export function RoadmapPage() {
  const { roadmapSlug = "" } = useParams();
  const query = useRoadmap(roadmapSlug);
  const startMutation = useStartRoadmap(roadmapSlug);
  const [startedOn, setStartedOn] = useState(currentLocalDate);
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow={`Roadmap / ${query.data.slug}`}
        title={query.data.title}
        description={query.data.description}
      />
      <div className="roadmap-summary">
        <Text className="technical-label" mb="sm">
          Общий прогресс
        </Text>
        <ProgressBar
          completed={query.data.completed_topics}
          total={query.data.total_topics}
          percent={query.data.progress_percent}
        />
      </div>
      <Paper withBorder p="lg">
        <Group justify="space-between" align="center">
          <Stack gap={4}>
            <Text fw={700}>
              {query.data.started_at
                ? `Прохождение начато ${formatDate(query.data.started_at)}`
                : `План обучения — ${formatDays(query.data.total_duration_days)}`}
            </Text>
            <Text size="sm" c="dimmed">
              {query.data.planned_completion_at
                ? `Плановое завершение — ${formatDate(query.data.planned_completion_at)}`
                : "Дедлайны разделов появятся после запуска роадмапа."}
            </Text>
          </Stack>
          {!query.data.started_at && (
            <Group align="flex-end">
              <TextInput
                label="Дата начала прохождения"
                type="date"
                value={startedOn}
                onChange={(event) => setStartedOn(event.currentTarget.value)}
                required
              />
              <Button
                loading={startMutation.isPending}
                disabled={!startedOn}
                onClick={() => startMutation.mutate(startedOn)}
              >
                Начать прохождение
              </Button>
            </Group>
          )}
        </Group>
        {startMutation.isError && (
          <Alert color="red" mt="md">
            Не удалось запустить роадмап. Попробуйте ещё раз.
          </Alert>
        )}
      </Paper>
      <Accordion
        multiple
        defaultValue={query.data.sections.map((section) => section.id)}
        className="brand-accordion"
      >
        {query.data.sections.map((section) => {
          const completed =
            section.topics.length > 0 &&
            section.topics.every((topic) => topic.status === "completed");
          const overdue =
            !completed &&
            section.deadline_at !== null &&
            new Date(section.deadline_at).getTime() < Date.now();
          return (
            <Accordion.Item key={section.id} value={section.id}>
              <Accordion.Control>
                <Group justify="space-between" wrap="nowrap" pr="md">
                  <Text fw={600}>{section.title}</Text>
                  {section.duration_days && (
                    <Group gap="xs" wrap="nowrap">
                      <Badge color={overdue ? "red" : "brandBlue"}>
                        {section.duration_days} дн.
                      </Badge>
                      {section.deadline_at && (
                        <Text size="xs" c={overdue ? "red" : "dimmed"}>
                          до {formatDate(section.deadline_at)}
                        </Text>
                      )}
                    </Group>
                  )}
                </Group>
              </Accordion.Control>
              <Accordion.Panel>
                <Stack>
                  {section.topics.length === 0 && (
                    <Text c="dimmed">В разделе пока нет тем.</Text>
                  )}
                  {section.topics.map((topic) => (
                    <Group
                      key={topic.id}
                      justify="space-between"
                      wrap="nowrap"
                      className="topic-row"
                    >
                      <div>
                        <Anchor
                          component={Link}
                          to={`/topics/${topic.id}`}
                          fw={600}
                        >
                          {topic.title}
                        </Anchor>
                        {topic.first_completed_at && (
                          <Text size="xs" c="dimmed">
                            Завершено{" "}
                            {new Date(topic.first_completed_at).toLocaleString(
                              "ru-RU",
                            )}
                          </Text>
                        )}
                      </div>
                      <TopicStatusBadge status={topic.status} />
                    </Group>
                  ))}
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          );
        })}
      </Accordion>
    </Stack>
  );
}
