import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  SimpleGrid,
  Stack,
  Text,
  Title,
} from "@mantine/core";

import type { ScheduleEventRead } from "../types/api";
import { formatMoscowDateTime, scheduleEventTiming } from "../utils/schedule";

interface Props {
  events: ScheduleEventRead[];
  emptyText?: string;
}

export function ScheduleEventList({
  events,
  emptyText = "Запланированных событий пока нет.",
}: Props) {
  if (events.length === 0) return <Text c="dimmed">{emptyText}</Text>;

  return (
    <SimpleGrid cols={{ base: 1, lg: 2 }}>
      {events.map((event) => {
        const isRescheduled = Boolean(
          event.kind === "weekly_call" &&
          event.is_rescheduled &&
          event.rescheduled_from &&
          event.next_occurrence_at,
        );

        return (
          <Card
            key={event.id}
            component="article"
            withBorder
            className={`schedule-event-card${
              isRescheduled ? " schedule-event-card--rescheduled" : ""
            }`}
            aria-label={`${event.title}${
              isRescheduled ? " — созвон перенесён" : ""
            }`}
          >
            <Stack gap="sm" h="100%">
              <Group justify="space-between" align="flex-start" wrap="wrap">
                <div className="schedule-event-heading">
                  <Title order={3}>{event.title}</Title>
                  <Text size="sm" c="dimmed" mt={4}>
                    {isRescheduled ? "Обычное расписание: " : ""}
                    {scheduleEventTiming(event)}
                  </Text>
                </div>
                <Group gap="xs" className="schedule-event-badges">
                  {isRescheduled && (
                    <Badge
                      color="brandYellow"
                      c="brandNavy.9"
                      size="lg"
                      variant="filled"
                    >
                      Созвон перенесён
                    </Badge>
                  )}
                  <Badge
                    color={event.kind === "meeting" ? "blue" : "brandYellow"}
                  >
                    {event.kind === "meeting" ? "Встреча" : "Каждую неделю"}
                  </Badge>
                </Group>
              </Group>

              <Group gap="xs">
                <Badge variant="light">{event.track.title}</Badge>
                <Badge variant="outline">
                  {event.source === "mentor"
                    ? `Ментор: ${event.source_name}`
                    : "Событие направления"}
                </Badge>
              </Group>

              {event.description && <Text size="sm">{event.description}</Text>}
              {event.kind === "weekly_call" &&
                event.next_occurrence_at &&
                (isRescheduled && event.rescheduled_from ? (
                  <Alert
                    color="brandYellow"
                    variant="light"
                    title="Созвон перенесён"
                    role="status"
                    aria-label="Созвон перенесён"
                    className="schedule-reschedule-alert"
                  >
                    <Stack gap="xs">
                      <div>
                        <Text
                          size="xs"
                          fw={700}
                          tt="uppercase"
                          className="technical-label"
                        >
                          Новая дата и время
                        </Text>
                        <Text
                          size="lg"
                          fw={700}
                          className="schedule-reschedule-new-time"
                        >
                          <time dateTime={event.next_occurrence_at}>
                            {formatMoscowDateTime(event.next_occurrence_at)}
                          </time>
                        </Text>
                      </div>
                      <Text component="div" size="sm" c="dimmed">
                        Было по расписанию:{" "}
                        <Text component="del" inherit>
                          {formatMoscowDateTime(event.rescheduled_from)}
                        </Text>
                      </Text>
                      <Text size="xs" c="dimmed">
                        Время указано по Москве
                      </Text>
                    </Stack>
                  </Alert>
                ) : (
                  <Text size="xs" c="dimmed">
                    Ближайший созвон:{" "}
                    {formatMoscowDateTime(event.next_occurrence_at)} по Москве
                  </Text>
                ))}
              {event.meeting_url && (
                <Button
                  component="a"
                  href={event.meeting_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  variant={isRescheduled ? "filled" : "light"}
                  fullWidth
                  mt="auto"
                >
                  Подключиться к встрече
                </Button>
              )}
            </Stack>
          </Card>
        );
      })}
    </SimpleGrid>
  );
}
