import {
  Badge,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { Link } from "react-router-dom";

import roadmapMascotUrl from "../assets/avatar-onboarding-roadmaps.jpg";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { ProgressBar } from "../components/ProgressBar";
import { PageHeader } from "../components/PageHeader";
import { useRoadmaps } from "../features/roadmaps/queries";
import { formatDays } from "../utils/formatDays";

export function RoadmapsPage() {
  const query = useRoadmaps();
  if (query.isPending) return <LoadingState label="Загружаем роадмапы…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  return (
    <Stack gap="xl">
      <Card className="brand-hero">
        <div className="brand-hero-content">
          <Text className="brand-eyebrow" mb="sm">
            Личный кабинет · учебные треки
          </Text>
          <Title order={1}>Время, потраченное не зря.</Title>
          <Text size="lg" mt="md" maw={600}>
            Понятный маршрут, практика и видимый прогресс — от первой темы до
            уверенного бэкенда.
          </Text>
        </div>
        <img
          src={roadmapMascotUrl}
          alt="Геральт"
          className="brand-hero-mascot"
          width={540}
          height={540}
          fetchPriority="high"
          decoding="async"
        />
      </Card>
      <PageHeader
        eyebrow="Ваш прогресс"
        title="Мои роадмапы"
        description="Продолжайте с того места, где остановились. Геральт всё запомнил."
      />
      {query.data.length === 0 ? (
        <Text c="dimmed">Доступных роадмапов пока нет.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {query.data.map((roadmap) => {
            const label =
              roadmap.progress_percent === 100
                ? "Завершён"
                : roadmap.started_at
                  ? "В процессе"
                  : "Не начат";
            return (
              <Card
                key={roadmap.id}
                withBorder
                component={Link}
                to={`/roadmaps/${roadmap.slug}`}
                style={{ textDecoration: "none", color: "inherit" }}
                className="roadmap-card"
              >
                <Stack h="100%">
                  <Group justify="space-between" align="flex-start">
                    <Badge
                      color={
                        roadmap.progress_percent === 100
                          ? "brandYellow"
                          : "brandBlue"
                      }
                      c={
                        roadmap.progress_percent === 100
                          ? "brandNavy.9"
                          : undefined
                      }
                    >
                      {label}
                    </Badge>
                    <Text className="roadmap-slug">TRACK / {roadmap.slug}</Text>
                  </Group>
                  <Title order={2}>{roadmap.title}</Title>
                  {roadmap.description && (
                    <Text c="dimmed">{roadmap.description}</Text>
                  )}
                  {roadmap.total_duration_days > 0 && (
                    <Text size="sm" c="dimmed">
                      План: {formatDays(roadmap.total_duration_days)}
                      {roadmap.planned_completion_at
                        ? ` · до ${new Date(roadmap.planned_completion_at).toLocaleDateString("ru-RU")}`
                        : ""}
                    </Text>
                  )}
                  <div style={{ marginTop: "auto" }}>
                    <ProgressBar
                      completed={roadmap.completed_topics}
                      total={roadmap.total_topics}
                      percent={roadmap.progress_percent}
                    />
                  </div>
                </Stack>
              </Card>
            );
          })}
        </SimpleGrid>
      )}
    </Stack>
  );
}
