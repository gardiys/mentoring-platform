import {
  Anchor,
  Badge,
  Card,
  Group,
  Select,
  SimpleGrid,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ProgressBar } from "../components/ProgressBar";
import { useMentorStudents } from "../features/mentor/queries";
import type { StudentLearningStatus } from "../types/api";

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

export function MentorStudentsPage() {
  const query = useMentorStudents();
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const students = useMemo(() => {
    const normalized = search.trim().toLocaleLowerCase("ru-RU");
    return (query.data ?? []).filter((student) => {
      const name = [student.first_name, student.last_name, student.email]
        .filter(Boolean)
        .join(" ")
        .toLocaleLowerCase("ru-RU");
      return (
        (!normalized || name.includes(normalized)) &&
        (!status || student.learning_status === status)
      );
    });
  }, [query.data, search, status]);

  if (query.isPending) return <LoadingState label="Загружаем учеников…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Менторская · текущая неделя"
        title="Мои ученики"
        description="Текущие темы, сроки, активность, собеседования и состояние каждого ученика."
      />
      <Group align="flex-end">
        <TextInput
          label="Поиск"
          placeholder="Имя или email"
          value={search}
          onChange={(event) => setSearch(event.currentTarget.value)}
          style={{ flex: 1 }}
        />
        <Select
          label="Статус"
          placeholder="Все статусы"
          clearable
          value={status}
          onChange={setStatus}
          data={Object.entries(statusLabels).map(([value, label]) => ({
            value,
            label,
          }))}
          w={{ base: "100%", sm: 260 }}
        />
      </Group>
      {students.length === 0 ? (
        <Text c="dimmed">Подходящих учеников нет.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, xl: 2 }}>
          {students.map((student) => (
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
                  </div>
                  <Group gap="xs" justify="flex-end">
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
    </Stack>
  );
}
