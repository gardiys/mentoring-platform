import { EmptyState } from "../components/EmptyState";
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
import { CardGridSkeleton } from "../components/CardGridSkeleton";
import { PageHeader } from "../components/PageHeader";
import { useAdminTracks } from "../features/admin/queries";

export function AdminTracksPage() {
  const query = useAdminTracks();
  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Админ-панель · Learning tracks"
          title="Треки обучения"
          description="Объединяйте роадмапы в направления Python и Go и управляйте доступом учеников."
        />
        <Button component={Link} to="/admin/tracks/new">
          + Создать трек
        </Button>
      </Group>

      {query.isPending ? (
        <CardGridSkeleton />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : query.data.length === 0 ? (
        <EmptyState
          title="Треков пока нет."
          description="Добавьте запись с помощью действий на этой странице."
        />
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {query.data.map((track) => (
            <Card
              key={track.id}
              withBorder
              className="roadmap-card admin-track-card"
            >
              <Stack gap="md">
                <Group justify="space-between">
                  <Badge
                    color={track.is_published ? "brandYellow" : "brandSand"}
                  >
                    {track.is_published ? "Доступен" : "Черновик"}
                  </Badge>
                  <Text className="roadmap-slug">/{track.slug}</Text>
                </Group>
                <div>
                  <Title order={2}>{track.title}</Title>
                  {track.description && (
                    <Text mt="xs">{track.description}</Text>
                  )}
                </div>
                <Group gap="xl">
                  <Text size="sm">
                    <b>{track.roadmaps.length}</b> роадмапов
                  </Text>
                  <Text size="sm">
                    <b>{track.student_ids.length}</b> учеников
                  </Text>
                </Group>
                <Group grow>
                  <Button
                    component={Link}
                    to={`/admin/tracks/${track.id}/edit`}
                    variant="light"
                  >
                    Настроить трек
                  </Button>
                  <Button
                    component={Link}
                    to={`/admin/schedule?track_id=${track.id}`}
                    variant="outline"
                  >
                    События направления
                  </Button>
                </Group>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
