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
import { useAdminInterviewDecks } from "../features/admin/interviewQueries";

export function AdminInterviewDecksPage() {
  const query = useAdminInterviewDecks();
  if (query.isPending) return <LoadingState label="Загружаем колоды…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Админ-панель · Собеседования"
          title="Редактор карточек"
          description="Создавайте отдельные колоды для Python и Go, отмечайте частые вопросы и публикуйте их ученикам."
        />
        <Button component={Link} to="/admin/interviews/new">
          + Создать колоду
        </Button>
      </Group>

      {query.data.length === 0 ? (
        <Text c="dimmed">Колод пока нет.</Text>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {query.data.map((deck) => {
            const frequent = deck.cards.filter(
              (card) => card.frequency === "frequent",
            ).length;
            return (
              <Card key={deck.id} withBorder className="roadmap-card">
                <Stack h="100%">
                  <Group justify="space-between">
                    <Group>
                      <Badge color="brandBlue">{deck.track_title}</Badge>
                      <Badge
                        color={deck.is_published ? "brandYellow" : "brandSand"}
                        c="brandNavy.9"
                      >
                        {deck.is_published ? "Опубликована" : "Черновик"}
                      </Badge>
                    </Group>
                    <Text className="roadmap-slug">/{deck.slug}</Text>
                  </Group>
                  <Title order={2}>{deck.title}</Title>
                  {deck.description && (
                    <Text c="dimmed">{deck.description}</Text>
                  )}
                  <Group mt="auto">
                    <Text size="sm">{deck.cards.length} карточек</Text>
                    <Text size="sm">{frequent} частых</Text>
                  </Group>
                  <Button
                    component={Link}
                    to={`/admin/interviews/${deck.id}/edit`}
                    variant="light"
                  >
                    Редактировать колоду
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
