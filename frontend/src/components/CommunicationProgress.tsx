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
  useCoachingAction,
  useCoachingHistory,
} from "../features/interviews/coaching";
import {
  comparableGroups,
  sortObservations,
} from "../features/interviews/coachingHistory";
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
  const observations = sortObservations(history.data.observations);
  if (!observations.length)
    return (
      <Text size="sm" c="dimmed">
        В последних {history.data.interview_count ?? 0} разборах нет
        подтверждённых наблюдений для сравнения.
        {history.data.truncated &&
          " Более ранние примеры доступны на страницах соответствующих разборов."}
      </Text>
    );
  const exercises = observations.filter(
    (o) =>
      o.decision !== "rejected" &&
      o.skill &&
      o.exercise &&
      (o.example_score ?? o.score) != null &&
      (o.example_score ?? o.score)! < 0.6,
  );
  const visibleExercises = exercises.filter(
    (o) => showCompleted || !o.completed_at,
  );
  const typeLabels: Record<string, string> = {
    hr: "HR-интервью",
    screening: "Скрининг",
    technical: "Техническое",
    final: "Финальное",
    system_design: "Проектирование систем",
    live_coding: "Написание кода",
    other: "Другое",
  };
  const groups = comparableGroups(observations);
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
        <Text size="sm" c="dimmed">
          Новые наблюдения и упражнения показаны первыми. История ограничена
          последними {history.data.limit ?? 30} разборами.
          {history.data.truncated &&
            " Более ранние примеры доступны на страницах соответствующих разборов."}
          Отметки практики относятся к текущей версии: после пересчёта разбора
          новый набор упражнений отмечается заново.
        </Text>
        {!groups.length && (
          <Text size="sm" c="dimmed">
            Для сравнения нужны хотя бы два оценённых наблюдения одного навыка в
            одинаковом формате интервью.
          </Text>
        )}
        {observations
          .filter((item) => item.decision === "rejected")
          .map((item) => (
            <Text
              key={`rejected:${item.interview_id}:${item.skill}`}
              size="sm"
              c="dimmed"
            >
              <Anchor
                component={Link}
                to={`/interviews/analysis/${item.interview_id}`}
              >
                {item.name} · {new Date(item.date).toLocaleDateString("ru")}
              </Anchor>
              {" — вывод отклонён ментором; исключён из сравнения и практики."}
            </Text>
          ))}
        {groups.map(([key, items]) => {
          const latest = items[0]!;
          return (
            <Stack
              key={key}
              gap="xs"
              className="analysis-communication-dimension"
            >
              <Group justify="space-between">
                <Text fw={700}>
                  {latest.name} ·{" "}
                  {typeLabels[latest.interview_type] ?? latest.interview_type}
                </Text>
              </Group>
              <Group gap="xs">
                {items.slice(0, 6).map((item) => (
                  <Anchor
                    key={item.interview_id}
                    component={Link}
                    to={`/interviews/analysis/${item.interview_id}`}
                    size="sm"
                  >
                    {new Date(item.date).toLocaleDateString("ru")} ·{" "}
                    {item.score == null
                      ? "—"
                      : `${Math.round(item.score * 100)}%`}
                    {` · ответов: ${item.observation_count ?? 1}`}
                  </Anchor>
                ))}
              </Group>
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
                  {item.name} · {new Date(item.date).toLocaleDateString("ru")}
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
