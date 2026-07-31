import { Anchor, Card, SimpleGrid, Stack, Text } from "@mantine/core";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { ProgressBar } from "../components/ProgressBar";
import { PageHeader } from "../components/PageHeader";
import { useMentorStudents } from "../features/mentor/queries";

export function MentorStudentsPage() {
  const query = useMentorStudents();
  if (query.isPending) return <LoadingState label="Загружаем учеников…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Менторская · текущий поток"
        title="Мои ученики"
        description="Прогресс, активность и учебные треки команды — в одном месте."
      />
      {query.data.length === 0 ? (
        <Text c="dimmed">Назначенных учеников пока нет.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {query.data.map((student) => (
            <Card key={student.id} withBorder className="student-card">
              <Stack>
                <Text className="technical-label">Student profile</Text>
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
                {student.roadmaps.map((roadmap) => (
                  <div key={roadmap.id}>
                    <Text size="sm" fw={600} mb={4}>
                      {roadmap.title}
                    </Text>
                    <ProgressBar
                      completed={roadmap.completed_topics}
                      total={roadmap.total_topics}
                      percent={roadmap.progress_percent}
                    />
                  </div>
                ))}
                <Text size="xs" c="dimmed">
                  Последняя активность:{" "}
                  {student.last_progress_at
                    ? new Date(student.last_progress_at).toLocaleString("ru-RU")
                    : "нет активности"}
                </Text>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
