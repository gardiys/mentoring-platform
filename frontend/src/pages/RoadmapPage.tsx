import {
  Accordion,
  Alert,
  Badge,
  Button,
  Group,
  Paper,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useEffect, useRef, useState } from "react";
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
  const [search, setSearch] = useState("");
  const [openedSections, setOpenedSections] = useState<string[]>([]);
  const initializedRoadmap = useRef<string | null>(null);

  useEffect(() => {
    if (!query.data || initializedRoadmap.current === query.data.id) return;
    initializedRoadmap.current = query.data.id;
    setOpenedSections(
      query.data.sections
        .filter(
          (section) =>
            section.topics.length === 0 ||
            section.topics.some((topic) => topic.status !== "completed"),
        )
        .map((section) => section.id),
    );
  }, [query.data]);

  if (query.isPending) return <LoadingState />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  const normalizedSearch = search.trim().toLocaleLowerCase("ru-RU");
  const visibleSections = query.data.sections.flatMap((section) => {
    if (!normalizedSearch) return [section];
    const sectionMatches = [section.title, section.description]
      .filter(Boolean)
      .some((value) =>
        value!.toLocaleLowerCase("ru-RU").includes(normalizedSearch),
      );
    const topics = sectionMatches
      ? section.topics
      : section.topics.filter((topic) =>
          [topic.title, topic.description]
            .filter(Boolean)
            .some((value) =>
              value!.toLocaleLowerCase("ru-RU").includes(normalizedSearch),
            ),
        );
    return sectionMatches || topics.length > 0 ? [{ ...section, topics }] : [];
  });

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
      <TextInput
        label="Поиск по темам"
        placeholder="Например: PostgreSQL, функции или Docker"
        value={search}
        onChange={(event) => setSearch(event.currentTarget.value)}
      />
      {normalizedSearch && (
        <Text size="sm" c="dimmed">
          Найдено тем:{" "}
          {visibleSections.reduce(
            (total, section) => total + section.topics.length,
            0,
          )}
        </Text>
      )}
      <Accordion
        multiple
        value={
          normalizedSearch
            ? visibleSections.map((section) => section.id)
            : openedSections
        }
        onChange={setOpenedSections}
        className="brand-accordion"
      >
        {visibleSections.map((section) => {
          const completed =
            section.topics.length > 0 &&
            section.topics.every((topic) => topic.status === "completed");
          const lastCompletedAt = completed
            ? section.topics.reduce<string | null>((latest, topic) => {
                if (!topic.last_completed_at) return latest;
                if (!latest || topic.last_completed_at > latest) {
                  return topic.last_completed_at;
                }
                return latest;
              }, null)
            : null;
          const overdue =
            !completed &&
            section.deadline_at !== null &&
            new Date(section.deadline_at).getTime() < Date.now();
          return (
            <Accordion.Item key={section.id} value={section.id}>
              <Accordion.Control>
                <Group
                  justify="space-between"
                  pr="md"
                  className="roadmap-section-heading"
                >
                  <Group gap="xs" className="min-width-zero">
                    <Text fw={600} className="roadmap-section-title">
                      {section.title}
                    </Text>
                    {completed && (
                      <Badge
                        color="brandGreen"
                        variant="filled"
                        leftSection="✓"
                      >
                        {lastCompletedAt
                          ? `Завершено ${formatDate(lastCompletedAt)}`
                          : "Завершено"}
                      </Badge>
                    )}
                  </Group>
                  {section.duration_days && (
                    <Group
                      gap="xs"
                      wrap="nowrap"
                      className="roadmap-section-meta"
                    >
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
                    <Link
                      key={topic.id}
                      to={`/topics/${topic.id}`}
                      className="topic-row"
                    >
                      <Group justify="space-between">
                        <div className="topic-row-main">
                          <Text fw={600}>{topic.title}</Text>
                          {topic.last_completed_at && (
                            <Text size="xs" c="dimmed">
                              Завершено{" "}
                              {new Date(topic.last_completed_at).toLocaleString(
                                "ru-RU",
                              )}
                            </Text>
                          )}
                        </div>
                        <TopicStatusBadge status={topic.status} />
                      </Group>
                    </Link>
                  ))}
                </Stack>
              </Accordion.Panel>
            </Accordion.Item>
          );
        })}
      </Accordion>
      {normalizedSearch && visibleSections.length === 0 && (
        <Paper withBorder p="lg">
          <Text fw={600}>Темы не найдены</Text>
          <Text size="sm" c="dimmed">
            Попробуйте сократить запрос или проверить написание.
          </Text>
        </Paper>
      )}
    </Stack>
  );
}
