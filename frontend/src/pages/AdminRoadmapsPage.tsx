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
import { notifications } from "@mantine/notifications";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  useAdminRoadmaps,
  useDeleteAdminRoadmap,
} from "../features/admin/queries";
import type { AdminRoadmapSummary } from "../types/api";

export function AdminRoadmapsPage() {
  const query = useAdminRoadmaps();
  const deleteRoadmap = useDeleteAdminRoadmap();
  if (query.isPending) return <LoadingState label="Загружаем роадмапы…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  const remove = (roadmap: AdminRoadmapSummary) => {
    if (
      !window.confirm(
        `Удалить роадмап «${roadmap.title}»? Это также удалит весь прогресс учеников по нему и отменить это будет нельзя.`,
      )
    )
      return;
    deleteRoadmap.mutate(roadmap.id, {
      onSuccess: () =>
        notifications.show({ color: "green", message: "Роадмап удалён" }),
      onError: (error) =>
        notifications.show({ color: "red", message: error.message }),
    });
  };

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
                    {roadmap.section_count} разделов · {roadmap.topic_count} тем
                  </Text>
                  <Group gap="xs">
                    <Button
                      component={Link}
                      to={`/admin/roadmaps/${roadmap.id}/edit`}
                      variant="light"
                      flex={1}
                    >
                      Редактировать
                    </Button>
                    <Button
                      variant="subtle"
                      color="red"
                      loading={
                        deleteRoadmap.isPending &&
                        deleteRoadmap.variables === roadmap.id
                      }
                      onClick={() => remove(roadmap)}
                    >
                      Удалить
                    </Button>
                  </Group>
                </Stack>
              </Card>
            );
          })}
        </SimpleGrid>
      )}
    </Stack>
  );
}
