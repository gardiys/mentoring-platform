import {
  Badge,
  Button,
  Card,
  Group,
  Progress,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useInterviewDecks } from "../features/interviews/queries";

export function InterviewsPage() {
  const query = useInterviewDecks();
  if (query.isPending) return <LoadingState label="Загружаем карточки…" />;
  if (query.isError) return <ErrorState retry={() => void query.refetch()} />;

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Подготовка · интервальные повторения"
        title="Собеседования"
        description="Вспоминайте ответ до переворота карточки. Частые вопросы попадутся первыми, а платформа сама назначит повторение."
      />

      {query.data.length === 0 ? (
        <Card withBorder>
          <Text c="dimmed">
            Для ваших учебных треков пока нет опубликованных колод.
          </Text>
        </Card>
      ) : (
        <SimpleGrid cols={{ base: 1, md: 2 }}>
          {query.data.map((deck) => (
            <Card key={deck.id} withBorder className="interview-deck-card">
              <Stack h="100%">
                <Group justify="space-between">
                  <Badge color="brandBlue">{deck.track_title}</Badge>
                  <Text className="technical-label">/{deck.slug}</Text>
                </Group>
                <Title order={2}>{deck.title}</Title>
                {deck.description && <Text c="dimmed">{deck.description}</Text>}
                <Stack gap={6} mt="auto">
                  {deck.stats.selected_categories === 0 ? (
                    <>
                      <Text fw={600}>Выберите пройденные темы</Text>
                      <Text size="sm" c="dimmed">
                        Доступно {deck.stats.available_cards} вопросов в{" "}
                        {deck.stats.total_categories} темах
                      </Text>
                    </>
                  ) : (
                    <>
                      <Group justify="space-between">
                        <Text size="sm" fw={600}>
                          Изучено {deck.stats.learned_cards} из{" "}
                          {deck.stats.total_cards}
                        </Text>
                        <Text className="technical-label">
                          {deck.stats.progress_percent}%
                        </Text>
                      </Group>
                      <Progress
                        value={deck.stats.progress_percent}
                        size="lg"
                        radius="xl"
                      />
                      <Group justify="space-between" mt="xs">
                        <Text size="sm" c="dimmed">
                          Осталось: {deck.stats.remaining_cards}
                        </Text>
                        {deck.stats.due_cards > 0 && (
                          <Badge color="brandYellow" c="brandNavy.9">
                            К повторению: {deck.stats.due_cards}
                          </Badge>
                        )}
                      </Group>
                      <Text size="xs" c="dimmed">
                        Выбрано тем: {deck.stats.selected_categories} из{" "}
                        {deck.stats.total_categories}
                      </Text>
                    </>
                  )}
                </Stack>
                <Button
                  component={Link}
                  to={`/interviews/${deck.slug}`}
                  mt="sm"
                >
                  {deck.stats.selected_categories === 0
                    ? "Выбрать темы"
                    : deck.stats.learned_cards === 0
                      ? "Начать изучение"
                      : "Продолжить"}
                </Button>
              </Stack>
            </Card>
          ))}
        </SimpleGrid>
      )}
    </Stack>
  );
}
