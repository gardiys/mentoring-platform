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
import { useAdminRoadmaps } from "../features/admin/queries";

export function AdminRoadmapsPage() {
  const query = useAdminRoadmaps();
  if (query.isPending) return <LoadingState label="Загружаем роадмапы…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Админ-панель · Content system"
          title="Конструктор роадмапов"
          description="Создавайте учебные модули, а затем включайте их в треки Python или Go."
        />
        <Button component={Link} to="/admin/roadmaps/new">
          + Создать роадмап
        </Button>
      </Group>
      {query.data.length === 0 ? (
        <Text c="dimmed">Роадмапов пока нет.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {query.data.map((roadmap) => {
            const topics = roadmap.sections.reduce(
              (total, section) => total + section.topics.length,
              0,
            );
            return (
              <Card
                key={roadmap.id}
                withBorder
                className="roadmap-card admin-roadmap-card"
              >
                <Stack gap="sm">
                  <Group justify="space-between">
                    <Badge
                      color={roadmap.is_published ? "brandYellow" : "brandSand"}
                      c="brandNavy.9"
                    >
                      {roadmap.is_published ? "Опубликован" : "Черновик"}
                    </Badge>
                    <Text className="roadmap-slug">
                      POS / {roadmap.position}
                    </Text>
                  </Group>
                  <div>
                    <Title order={2}>{roadmap.title}</Title>
                    <Text className="roadmap-slug" mt={4}>
                      /{roadmap.slug}
                    </Text>
                  </div>
                  {roadmap.description && <Text>{roadmap.description}</Text>}
                  <Text size="sm">
                    {roadmap.sections.length} разделов · {topics} тем
                  </Text>
                  <Button
                    component={Link}
                    to={`/admin/roadmaps/${roadmap.id}/edit`}
                    variant="light"
                  >
                    Редактировать
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
