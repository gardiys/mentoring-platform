import {
  Anchor,
  Badge,
  Card,
  Group,
  MultiSelect,
  Pagination,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ProgressBar } from "../components/ProgressBar";
import { TelegramChatLink } from "../components/TelegramChatLink";
import { useMentorStudents } from "../features/mentor/queries";
import type { StudentAccessFilter, StudentLearningStatus } from "../types/api";

const statusLabels: Record<StudentLearningStatus, string> = {
  learning: "Учится",
  interviewing: "Ходит на собеседования",
  probation: "Работает на испыталке",
  finished: "Обучение завершено",
};

const levelLabels = {
  weak: "Слабый",
  medium: "Средний",
  strong: "Сильный",
} as const;

function formatActivity(value: string | null): string {
  return value
    ? new Date(value).toLocaleString("ru-RU")
    : "активности пока не было";
}

function personName(firstName: string, lastName: string | null): string {
  return [firstName, lastName].filter(Boolean).join(" ");
}

export function MentorStudentsPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search.trim(), 250);
  const [trackId, setTrackId] = useState<string | null>(null);
  const [statuses, setStatuses] = useState<StudentLearningStatus[]>([]);
  const [access, setAccess] = useState<StudentAccessFilter>("active");
  const [mentorFilter, setMentorFilter] = useState("all");
  const [page, setPage] = useState(1);
  const query = useMentorStudents({
    query: debouncedSearch,
    trackId,
    mentorFilter,
    access,
    learningStatuses: statuses,
    page,
  });

  useEffect(
    () => setPage(1),
    [debouncedSearch, trackId, statuses, access, mentorFilter],
  );

  if (query.isPending) return <LoadingState label="Загружаем учеников…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Менторская · текущая неделя"
        title="Мои ученики"
        description="Текущие темы, сроки, активность, собеседования и состояние каждого ученика."
      />
      <Group align="flex-end" grow>
        <TextInput
          label="Поиск"
          placeholder="Имя или email"
          value={search}
          onChange={(event) => setSearch(event.currentTarget.value)}
        />
        <Select
          label="Направление"
          placeholder="Python и Go"
          clearable
          searchable
          value={trackId}
          onChange={setTrackId}
          data={query.data.directions.map((direction) => ({
            value: direction.id,
            label: direction.title,
          }))}
          w={{ base: "100%", sm: 240 }}
        />
        <MultiSelect
          label="Текущий статус"
          placeholder="Все статусы"
          clearable
          value={statuses}
          onChange={(values) => setStatuses(values as StudentLearningStatus[])}
          data={Object.entries(statusLabels).map(([value, label]) => ({
            value,
            label,
          }))}
          w={{ base: "100%", sm: 340 }}
        />
        <Select
          label="Доступ"
          value={access}
          onChange={(value) =>
            setAccess((value as StudentAccessFilter | null) ?? "active")
          }
          data={[
            { value: "active", label: "Доступ открыт" },
            { value: "blocked", label: "Доступ закрыт" },
            { value: "all", label: "Любой доступ" },
          ]}
          w={{ base: "100%", sm: 220 }}
        />
        {query.data.can_filter_by_mentor && (
          <Select
            label="Ментор"
            value={mentorFilter}
            onChange={(value) => setMentorFilter(value ?? "all")}
            searchable
            data={[
              { value: "all", label: "Все менторы" },
              { value: "unassigned", label: "Без ментора" },
              ...query.data.mentors.map((mentor) => ({
                value: mentor.id,
                label: `${personName(mentor.first_name, mentor.last_name)}${mentor.role === "admin" ? " · администратор" : ""}`,
              })),
            ]}
            w={{ base: "100%", sm: 260 }}
          />
        )}
      </Group>
      <Text fw={600}>Найдено учеников: {query.data.total}</Text>
      {query.data.items.length === 0 ? (
        <Text c="dimmed">Подходящих учеников нет.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, xl: 2 }}>
          {query.data.items.map((student) => (
            <Card
              key={student.id}
              withBorder
              className="student-card"
              style={
                student.is_overdue
                  ? {
                      borderColor: "var(--mantine-color-red-6)",
                      boxShadow: "inset 4px 0 var(--mantine-color-red-6)",
                    }
                  : undefined
              }
            >
              <Stack>
                <Group justify="space-between" align="flex-start">
                  <div>
                    <Anchor
                      component={Link}
                      to={`/mentor/students/${student.id}`}
                      fw={700}
                      size="lg"
                    >
                      {[student.first_name, student.last_name]
                        .filter(Boolean)
                        .join(" ")}
                    </Anchor>
                    <Text c="dimmed" size="sm">
                      {student.email ?? "Email не указан"}
                    </Text>
                    <TelegramChatLink username={student.telegram_username} />
                  </div>
                  <Group gap="xs" justify="flex-end">
                    <Badge
                      color={student.is_active ? "green" : "red"}
                      variant="outline"
                    >
                      {student.is_active ? "Доступ открыт" : "Доступ закрыт"}
                    </Badge>
                    {student.is_overdue && <Badge color="red">Не в срок</Badge>}
                    <Badge variant="light">
                      {statusLabels[student.learning_status]}
                    </Badge>
                    {student.strength_level && (
                      <Badge color="gray" variant="outline">
                        {levelLabels[student.strength_level]}
                      </Badge>
                    )}
                  </Group>
                </Group>

                {student.current_topics.length > 0 ? (
                  <Stack gap={6}>
                    <Text className="technical-label">Сейчас изучает</Text>
                    {student.current_topics.map((topic) => (
                      <Group
                        key={topic.id}
                        justify="space-between"
                        wrap="nowrap"
                      >
                        <div>
                          <Text size="sm" fw={600}>
                            {topic.title}
                          </Text>
                          <Text size="xs" c="dimmed">
                            {topic.roadmap_title} · {topic.section_title}
                          </Text>
                        </div>
                        <Badge color={topic.is_overdue ? "red" : "blue"}>
                          {topic.days_in_topic === 0
                            ? "сегодня"
                            : `${topic.days_in_topic} дн.`}
                        </Badge>
                      </Group>
                    ))}
                  </Stack>
                ) : (
                  <Text size="sm" c="dimmed">
                    Активная тема не отмечена
                  </Text>
                )}

                {student.roadmaps.map((roadmap) => (
                  <div key={roadmap.id}>
                    <Group justify="space-between" mb={4}>
                      <Text size="sm" fw={600}>
                        {roadmap.title}
                      </Text>
                      {roadmap.overdue_sections > 0 && (
                        <Text size="xs" c="red" fw={600}>
                          Просрочено разделов: {roadmap.overdue_sections}
                        </Text>
                      )}
                    </Group>
                    <ProgressBar
                      completed={roadmap.completed_topics}
                      total={roadmap.total_topics}
                      percent={roadmap.progress_percent}
                    />
                  </div>
                ))}

                <Group justify="space-between">
                  <Text size="xs" c="dimmed">
                    За 7 дней завершено тем:{" "}
                    {student.completed_topics_this_week}
                  </Text>
                  <Text size="xs" c="dimmed">
                    Моков проведено: {student.mock_interview_count}
                  </Text>
                </Group>
                <Text size="xs" c="dimmed">
                  Последняя активность:{" "}
                  {formatActivity(student.last_progress_at)}
                </Text>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
      {query.data.total > query.data.limit && (
        <Pagination
          value={page}
          onChange={setPage}
          total={Math.ceil(query.data.total / query.data.limit)}
          mx="auto"
        />
      )}
    </Stack>
  );
}
