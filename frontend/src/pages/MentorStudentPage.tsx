import { Accordion, Group, Stack, Text, Title } from "@mantine/core";
import { useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { ProgressBar } from "../components/ProgressBar";
import { PageHeader } from "../components/PageHeader";
import { TopicStatusBadge } from "../components/TopicStatusBadge";
import { useMentorStudent } from "../features/mentor/queries";

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

export function MentorStudentPage() {
  const { studentId = "" } = useParams();
  const query = useMentorStudent(studentId);
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Карточка ученика"
        title={[query.data.first_name, query.data.last_name]
          .filter(Boolean)
          .join(" ")}
        description={query.data.email ?? "Email не указан"}
      />
      {query.data.roadmaps.length === 0 && (
        <Text c="dimmed">Роадмапы не назначены.</Text>
      )}
      {query.data.roadmaps.map((roadmap) => (
        <Stack key={roadmap.id} className="student-roadmap">
          <Title order={2}>{roadmap.title}</Title>
          <ProgressBar
            completed={roadmap.completed_topics}
            total={roadmap.total_topics}
            percent={roadmap.progress_percent}
          />
          <Accordion multiple className="brand-accordion">
            {roadmap.sections.map((section) => (
              <Accordion.Item key={section.id} value={section.id}>
                <Accordion.Control>{section.title}</Accordion.Control>
                <Accordion.Panel>
                  <Stack>
                    {section.topics.map((topic) => (
                      <div key={topic.id} className="topic-row">
                        <Group justify="space-between">
                          <Text fw={600}>{topic.title}</Text>
                          <TopicStatusBadge status={topic.status} />
                        </Group>
                        <Text size="xs" c="dimmed">
                          Первое завершение:{" "}
                          {formatDate(topic.first_completed_at)} · Последнее:{" "}
                          {formatDate(topic.last_completed_at)}
                        </Text>
                      </div>
                    ))}
                  </Stack>
                </Accordion.Panel>
              </Accordion.Item>
            ))}
          </Accordion>
        </Stack>
      ))}
    </Stack>
  );
}
