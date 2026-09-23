import {
  Alert,
  Button,
  Card,
  Group,
  Progress,
  Stack,
  Text,
} from "@mantine/core";
import type { ReviewQueue } from "./useReviewQueue";

export function ReviewQueueProgress({ queue }: { queue: ReviewQueue }) {
  const remaining = queue.total - queue.completed;
  return (
    <Card withBorder>
      <Stack gap="xs">
        {queue.query.isError ? (
          <Alert color="yellow" title="Не удалось загрузить очередь">
            <Button
              variant="subtle"
              onClick={() => void queue.refresh()}
              disabled={queue.busy || queue.query.isFetching}
            >
              Повторить загрузку очереди
            </Button>
          </Alert>
        ) : (
          <>
            <Group justify="space-between">
              <Text fw={600} aria-live="polite">
                {queue.query.isPending
                  ? "Загружаем очередь проверки…"
                  : queue.total === 0
                    ? "В этой очереди нет карточек"
                    : remaining === 0
                      ? "Очередь проверена"
                      : `Осталось в этой очереди: ${remaining} из ${queue.total}`}
              </Text>
              <Text size="sm" c="dimmed">
                Завершено: {queue.completed}
              </Text>
            </Group>
            <Progress
              aria-label="Прогресс проверки очереди"
              value={
                queue.total
                  ? (queue.completed / queue.total) * 100
                  : queue.query.isPending
                    ? 0
                    : 100
              }
            />
          </>
        )}
        <Group justify="space-between">
          <Group>
            <Button
              variant="default"
              onClick={queue.previous}
              disabled={
                queue.busy || queue.query.isFetching || !queue.previousId
              }
            >
              ← Предыдущая
            </Button>
            <Button
              variant="light"
              onClick={queue.next}
              disabled={queue.busy || queue.query.isFetching || !queue.nextId}
            >
              Пропустить →
            </Button>
          </Group>
          <Button
            variant="subtle"
            onClick={() => void queue.refresh()}
            disabled={queue.busy || queue.query.isFetching}
          >
            Обновить очередь
          </Button>
        </Group>
        <Text size="xs" c="dimmed">
          Пропуск оставляет карточку нерешённой. Alt + ← / → — переход, Ctrl / ⌘
          + Enter — создать карточку.
        </Text>
      </Stack>
    </Card>
  );
}
