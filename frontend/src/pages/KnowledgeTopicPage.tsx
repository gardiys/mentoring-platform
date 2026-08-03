import {
  Anchor,
  Badge,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { Link, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useKnowledgeTopic } from "../features/knowledge/queries";
import type { KnowledgeEntryKind } from "../types/api";

const sections: Array<{
  kind: KnowledgeEntryKind;
  title: string;
  empty: string;
}> = [
  {
    kind: "article",
    title: "Статьи и разборы",
    empty: "Статей в этой теме пока нет.",
  },
  {
    kind: "question",
    title: "Вопросы для обсуждения",
    empty: "Вопросов пока нет.",
  },
];

export function KnowledgeTopicPage() {
  const { topicSlug = "" } = useParams();
  const query = useKnowledgeTopic(topicSlug);
  if (query.isPending) return <LoadingState />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  return (
    <Stack gap="xl">
      <Anchor component={Link} to="/knowledge">
        ← Все темы базы знаний
      </Anchor>
      <PageHeader
        eyebrow={`Knowledge topic / ${query.data.slug}`}
        title={query.data.title}
        description={query.data.description}
      />
      {sections.map((section) => {
        const entries = query.data.entries.filter(
          (entry) => entry.kind === section.kind,
        );
        return (
          <Stack key={section.kind}>
            <Group>
              <Title order={2}>{section.title}</Title>
              <Badge
                color={
                  section.kind === "question" ? "brandYellow" : "brandBlue"
                }
              >
                {entries.length}
              </Badge>
            </Group>
            {entries.length === 0 ? (
              <Text c="dimmed">{section.empty}</Text>
            ) : (
              <SimpleGrid cols={{ base: 1, md: 2 }}>
                {entries.map((entry) => (
                  <Card
                    key={entry.id}
                    withBorder
                    component={Link}
                    to={`/knowledge/entries/${entry.slug}`}
                    className="knowledge-entry-card"
                    style={{ textDecoration: "none", color: "inherit" }}
                  >
                    <Stack gap="xs">
                      <Text className="roadmap-slug">/{entry.slug}</Text>
                      <Title order={3}>{entry.title}</Title>
                      {entry.summary && <Text c="dimmed">{entry.summary}</Text>}
                    </Stack>
                  </Card>
                ))}
              </SimpleGrid>
            )}
          </Stack>
        );
      })}
    </Stack>
  );
}
