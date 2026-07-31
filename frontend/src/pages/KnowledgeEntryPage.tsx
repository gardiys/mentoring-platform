import {
  Anchor,
  Badge,
  Breadcrumbs,
  Group,
  Paper,
  Stack,
  Text,
} from "@mantine/core";
import ReactMarkdown from "react-markdown";
import { Link, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useKnowledgeEntry } from "../features/knowledge/queries";

export function KnowledgeEntryPage() {
  const { entrySlug = "" } = useParams();
  const query = useKnowledgeEntry(entrySlug);
  if (query.isPending) return <LoadingState />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;

  return (
    <Stack gap="xl">
      <Breadcrumbs>
        <Anchor component={Link} to="/knowledge">
          База знаний
        </Anchor>
        <Anchor
          component={Link}
          to={`/knowledge/topics/${query.data.topic.slug}`}
        >
          {query.data.topic.title}
        </Anchor>
        <Text>{query.data.title}</Text>
      </Breadcrumbs>
      <PageHeader
        eyebrow={`${query.data.kind === "question" ? "Вопрос" : "Статья"} · ${query.data.topic.title}`}
        title={query.data.title}
        description={query.data.summary}
      />
      <Group>
        <Badge
          color={query.data.kind === "question" ? "brandYellow" : "brandBlue"}
        >
          {query.data.kind === "question"
            ? "Вопрос для обсуждения"
            : "Учебная статья"}
        </Badge>
        <Text className="technical-label">
          Обновлено{" "}
          {new Date(query.data.updated_at).toLocaleDateString("ru-RU")}
        </Text>
      </Group>
      <Paper
        withBorder
        p={{ base: "md", sm: "xl" }}
        className="markdown-content"
      >
        <ReactMarkdown>{query.data.content_markdown}</ReactMarkdown>
      </Paper>
    </Stack>
  );
}
