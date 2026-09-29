import { Badge, Button, Card, Group, Stack, Text, Title } from "@mantine/core";
import type { IntelligenceInterviewDetail } from "../types/api";
import {
  communicationLabels,
  useCoachingAction,
} from "../features/interviews/coaching";

export function CommunicationFeedback({
  interview,
  onSeek,
  canReview,
  isOwner,
}: {
  interview: IntelligenceInterviewDetail;
  onSeek: (ms: number) => void;
  canReview: boolean;
  isOwner: boolean;
}) {
  const action = useCoachingAction();
  const overview = interview.overview!;
  const dimensions = overview.communication_grounded
    ? overview.communication_dimensions
    : [];
  const moments = (ids: string[]) =>
    ids
      .map((id) => interview.transcript.find((u) => u.id === id))
      .filter((u) => !!u);
  return (
    <Card withBorder>
      <Stack gap="md">
        <Title order={2}>Коммуникация и подача</Title>
        <Text>
          {overview.communication_grounded
            ? overview.communication_summary
            : "Недостаточно подтверждённых реплик для оценки коммуникации."}
        </Text>
        {dimensions.map((dimension) => {
          if (!dimension.skill) return null;
          const skill = dimension.skill;
          const state = overview.coaching_state?.[skill];
          const mutate = (
            kind: "complete" | "uncomplete" | "approve" | "reject",
          ) =>
            action.mutate({
              interviewId: interview.id,
              skill,
              revision: interview.analysis_revision ?? 1,
              action: kind,
            });
          return (
            <Stack
              key={skill}
              gap="xs"
              className="analysis-communication-dimension"
            >
              <Group justify="space-between">
                <Text fw={700}>{communicationLabels[skill]}</Text>
                {dimension.score !== null && (
                  <Badge variant="outline">
                    {Math.round(dimension.score * 100)}%
                  </Badge>
                )}
              </Group>
              <Text size="sm">{dimension.summary}</Text>
              <Text component="blockquote" m={0} size="sm">
                «{dimension.evidence_quote}»
              </Text>
              <Group gap="xs">
                {moments(dimension.evidence_utterance_ids).map((u) => (
                  <Button
                    key={u.id}
                    variant="subtle"
                    size="xs"
                    onClick={() => onSeek(u.start_ms)}
                  >
                    К записи · {Math.floor(u.start_ms / 60000)}:
                    {String(Math.floor(u.start_ms / 1000) % 60).padStart(
                      2,
                      "0",
                    )}
                  </Button>
                ))}
              </Group>
              {dimension.rewrite && (
                <>
                  <Text size="sm">
                    <b>Ты сказал:</b> {dimension.rewrite.original}
                  </Text>
                  <Text size="sm">
                    <b>Лучше сказать так:</b> {dimension.rewrite.improved}
                  </Text>
                </>
              )}
              {dimension.exercise && (
                <>
                  <Text size="sm">
                    <b>Попробуй:</b> {dimension.exercise.task}
                  </Text>
                  <Text size="sm" c="dimmed">
                    Готово, когда: {dimension.exercise.success_criterion}
                  </Text>
                  {isOwner && (
                    <Button
                      variant="light"
                      size="xs"
                      loading={action.isPending}
                      onClick={() =>
                        mutate(state?.completed_at ? "uncomplete" : "complete")
                      }
                    >
                      {state?.completed_at
                        ? "Выполнено · повторить"
                        : "Отметить выполненным"}
                    </Button>
                  )}
                </>
              )}
              {canReview && (
                <Group>
                  <Button
                    size="xs"
                    variant="light"
                    loading={action.isPending}
                    onClick={() => mutate("approve")}
                  >
                    {state?.decision === "approved"
                      ? "Подтверждено ментором"
                      : "Подтвердить вывод"}
                  </Button>
                  <Button
                    size="xs"
                    variant="subtle"
                    color="red"
                    loading={action.isPending}
                    onClick={() => mutate("reject")}
                  >
                    Отклонить вывод
                  </Button>
                </Group>
              )}
            </Stack>
          );
        })}
        {canReview &&
          Object.entries(overview.coaching_state ?? {})
            .filter(([, s]) => s.decision === "rejected")
            .map(([skill]) => (
              <Group key={skill}>
                <Text size="sm">
                  Вывод отклонён:{" "}
                  {communicationLabels[
                    skill as keyof typeof communicationLabels
                  ] ?? skill}
                </Text>
                <Button
                  size="xs"
                  variant="subtle"
                  loading={action.isPending}
                  onClick={() =>
                    action.mutate({
                      interviewId: interview.id,
                      revision: interview.analysis_revision ?? 1,
                      skill: skill as keyof typeof communicationLabels,
                      action: "approve",
                    })
                  }
                >
                  Восстановить
                </Button>
              </Group>
            ))}
        {overview.candidate_questions?.length === 0 && (
          <Text size="sm" c="dimmed">
            В доступной записи твои вопросы работодателю не выделены.
          </Text>
        )}
        {!!overview.candidate_questions?.length && (
          <>
            <Title order={3}>Твои вопросы работодателю</Title>
            <Text size="sm" c="dimmed">
              Сохранили отдельно от вопросов для карточек. На следующем интервью
              можно уточнить непрояснённые условия роли и работы команды.
            </Text>
            {overview.candidate_questions.map((q, i) => (
              <Stack key={i} gap="xs">
                <Text>«{q.evidence_quote}»</Text>
                <Group>
                  {moments(q.question_utterance_ids).map((u) => (
                    <Button
                      size="xs"
                      variant="subtle"
                      key={u.id}
                      onClick={() => onSeek(u.start_ms)}
                    >
                      Послушать вопрос
                    </Button>
                  ))}
                </Group>
                {moments(q.response_utterance_ids).map((u) => (
                  <Text key={u.id} size="sm" c="dimmed">
                    Ответ: {u.text}
                  </Text>
                ))}
              </Stack>
            ))}
          </>
        )}
      </Stack>
    </Card>
  );
}
