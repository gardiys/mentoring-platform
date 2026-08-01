import {
  Badge,
  Button,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useAdminKnowledgeTopics } from "../features/admin/knowledgeQueries";

export function AdminKnowledgeTopicsPage() {
  const query = useAdminKnowledgeTopics();
  if (query.isPending) return <LoadingState label="Загружаем базу знаний…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Админ-панель · Knowledge base"
          title="Редактор базы знаний"
          description="Создавайте темы, статьи и вопросы для работы с учениками."
        />
        <Button component={Link} to="/admin/knowledge/new">
          + Создать тему
        </Button>
      </Group>
      {query.data.length === 0 ? (
        <Text c="dimmed">Тем пока нет.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {query.data.map((topic) => {
            return (
              <Card
                key={topic.id}
                withBorder
                className="roadmap-card admin-knowledge-card"
              >
                <Stack>
                  <Group justify="space-between">
                    <Badge
                      color={topic.is_published ? "brandYellow" : "brandSand"}
                      c="brandNavy.9"
                    >
                      {topic.is_published ? "Опубликована" : "Черновик"}
                    </Badge>
                    <Text className="roadmap-slug">/{topic.slug}</Text>
                  </Group>
                  <Title order={2}>{topic.title}</Title>
                  {topic.description && (
                    <Text c="dimmed">{topic.description}</Text>
                  )}
                  <Group>
                    <Text size="sm">{topic.article_count} статей</Text>
                    <Text size="sm">{topic.question_count} вопросов</Text>
                  </Group>
                  <Button
                    component={Link}
                    to={`/admin/knowledge/${topic.id}/edit`}
                    variant="light"
                  >
                    Редактировать материалы
                  </Button>
                </Stack>
              </Card>
            );
          })}
        </SimpleGrid>
      )}
    </Stack>
  );
}
