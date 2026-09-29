import {
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Stack,
  Text,
  Title,
  Switch,
} from "@mantine/core";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useMe } from "../features/auth/queries";
import {
  communicationLabels,
  useCoachingAction,
  useCoachingHistory,
  type CoachingObservation,
} from "../features/interviews/coaching";
import { ErrorState } from "./ErrorState";

export function CommunicationProgress({
  studentId,
  practice = false,
}: {
  studentId?: string;
  practice?: boolean;
}) {
  const [showCompleted, setShowCompleted] = useState(false);
  const [limit, setLimit] = useState(10);
  const me = useMe();
  const id = studentId ?? me.data?.id;
  const history = useCoachingHistory(id);
  const action = useCoachingAction();
  if (history.isPending)
    return (
      <Text c="dimmed" role="status">
        Загружаем практику коммуникации…
      </Text>
    );
  if (history.isError)
    return (
      <ErrorState error={history.error} retry={() => void history.refetch()} />
    );
  const observations = history.data.observations;
  if (!observations.length)
    return (
      <Text size="sm" c="dimmed">
        Динамика коммуникации появится после разборов с подтверждёнными
        цитатами.
      </Text>
    );
  const exercises = observations.filter(
    (o) => o.skill && o.exercise && o.score !== null && o.score < 0.6,
  );
  const visibleExercises = exercises
    .filter((o) => showCompleted || !o.completed_at)
    .slice()
    .reverse();
  const typeLabels: Record<string, string> = {
    hr: "HR-интервью",
    screening: "Скрининг",
    technical: "Техническое",
    final: "Финальное",
    system_design: "Проектирование систем",
    live_coding: "Написание кода",
    other: "Другое",
  };
  const groups = new Map<string, CoachingObservation[]>();
  for (const item of observations) {
    if (!item.skill) continue;
    const key = `${item.skill}:${item.interview_type}`;
    groups.set(key, [...(groups.get(key) ?? []), item]);
  }
  return (
    <Card withBorder>
      <Stack>
        <Title order={2}>
          {practice ? "Практика коммуникации" : "Динамика коммуникации"}
        </Title>
        <Text size="sm" c="dimmed">
          Сравниваем наблюдения одного навыка в одинаковом формате интервью.
          Выполнение упражнения — твоя отметка практики, а не повышение
          AI-оценки.
        </Text>
        {[...groups.entries()].map(([key, items]) => {
          const latest = items.at(-1)!;
          const first = items.find((i) => i.score !== null);
          const delta =
            first?.score != null && latest.score !== null && items.length > 1
              ? Math.round((latest.score - first.score) * 100)
              : null;
          const repeated =
            items.length >= 3 &&
            items.slice(-3).every((i) => i.score !== null && i.score < 0.6);
          return (
            <Stack
              key={key}
              gap="xs"
              className="analysis-communication-dimension"
            >
              <Group justify="space-between">
                <Text fw={700}>
                  {communicationLabels[latest.skill!]} ·{" "}
                  {typeLabels[latest.interview_type] ?? latest.interview_type}
                </Text>
                {delta !== null && (
                  <Badge
                    color={delta > 0 ? "green" : delta < 0 ? "orange" : "gray"}
                  >
                    {delta > 0 ? "+" : ""}
                    {delta} п.п.
                  </Badge>
                )}
              </Group>
              <Group gap="xs">
                {items.slice(-6).map((item) => (
                  <Anchor
                    key={item.interview_id}
                    component={Link}
                    to={`/interviews/analysis/${item.interview_id}`}
                    size="sm"
                  >
                    {new Date(item.date).toLocaleDateString("ru")} ·{" "}
                    {item.score === null
                      ? "—"
                      : `${Math.round(item.score * 100)}%`}
                  </Anchor>
                ))}
              </Group>
              {repeated && (
                <Text c="orange" size="sm">
                  Три разбора подряд есть пробел — стоит потренировать с
                  ментором.
                </Text>
              )}
              {latest.completed_at && (
                <Badge color="green">Практика выполнена</Badge>
              )}
            </Stack>
          );
        })}
        {practice && (
          <>
            <Group justify="space-between">
              <Text fw={700}>
                Выполнено {exercises.filter((e) => e.completed_at).length} из{" "}
                {exercises.length}
              </Text>
              <Switch
                label="Показать выполненные"
                checked={showCompleted}
                onChange={(e) => setShowCompleted(e.currentTarget.checked)}
              />
            </Group>
            {visibleExercises.slice(0, limit).map((item) => (
              <Stack
                key={`${item.interview_id}:${item.skill}`}
                gap="xs"
                className="analysis-communication-dimension"
              >
                <Anchor
                  component={Link}
                  to={`/interviews/analysis/${item.interview_id}`}
                >
                  {communicationLabels[item.skill!]} ·{" "}
                  {new Date(item.date).toLocaleDateString("ru")}
                </Anchor>
                <Text size="sm">{item.exercise!.task}</Text>
                <Text c="dimmed" size="sm">
                  Готово, когда: {item.exercise!.success_criterion}
                </Text>
                {me.data?.id === id && (
                  <Button
                    size="xs"
                    variant="light"
                    loading={action.isPending}
                    onClick={() =>
                      action.mutate({
                        interviewId: item.interview_id,
                        skill: item.skill!,
                        revision: item.analysis_revision,
                        action: item.completed_at ? "uncomplete" : "complete",
                      })
                    }
                  >
                    {item.completed_at
                      ? "Выполнено · повторить"
                      : "Отметить выполненным"}
                  </Button>
                )}
              </Stack>
            ))}
            {visibleExercises.length > limit && (
              <Button variant="subtle" onClick={() => setLimit(limit + 10)}>
                Показать ещё упражнения
              </Button>
            )}
            {!visibleExercises.length && (
              <Text c="dimmed">Нет невыполненных упражнений.</Text>
            )}
          </>
        )}
      </Stack>
    </Card>
  );
}
