import {
  Anchor,
  Badge,
  Card,
  Group,
  Progress,
  SegmentedControl,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Title,
} from "@mantine/core";
import { Link } from "react-router-dom";

import { useMentorInterviewAnalytics } from "../features/mentor/queries";
import type {
  InterviewStageType,
  MentorAnalyticsPeriod,
  StudentAccessFilter,
  StudentLearningStatus,
} from "../types/api";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { TelegramChatLink } from "./TelegramChatLink";

const stageLabels: Record<InterviewStageType, string> = {
  screening: "Скрининги",
  technical_screening: "Технические скрининги",
  technical_interview: "Технические интервью",
  system_design: "Системный дизайн",
  final_interview: "Финальные интервью",
  other: "Другие этапы",
};

const periodLabels: Record<MentorAnalyticsPeriod, string> = {
  week: "Последние 7 дней",
  month: "Последние 30 дней",
  all: "Всё время",
};

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleDateString("ru-RU") : "—";
}

function personName(firstName: string, lastName: string | null): string {
  return [firstName, lastName].filter(Boolean).join(" ");
}

function MetricCard({
  label,
  value,
  hint,
  color,
}: {
  label: string;
  value: string | number;
  hint?: string;
  color?: string;
}) {
  return (
    <Card withBorder>
      <Stack gap={6}>
        <Text className="technical-label">{label}</Text>
        <Title order={2} c={color}>
          {value}
        </Title>
        {hint && (
          <Text size="xs" c="dimmed">
            {hint}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

function RateRow({
  label,
  value,
  description,
}: {
  label: string;
  value: number;
  description: string;
}) {
  return (
    <Stack gap={6}>
      <Group justify="space-between" wrap="nowrap">
        <div>
          <Text fw={700}>{label}</Text>
          <Text size="xs" c="dimmed">
            {description}
          </Text>
        </div>
        <Badge variant="light" size="lg">
          {value}%
        </Badge>
      </Group>
      <Progress value={Math.min(100, value)} size="sm" radius="xl" />
    </Stack>
  );
}

export function MentorInterviewAnalytics({
  period,
  onPeriodChange,
  trackId,
  mentorFilter,
  access,
  learningStatuses,
}: {
  period: MentorAnalyticsPeriod;
  onPeriodChange: (period: MentorAnalyticsPeriod) => void;
  trackId: string | null;
  mentorFilter: string;
  access: StudentAccessFilter;
  learningStatuses: StudentLearningStatus[];
}) {
  const query = useMentorInterviewAnalytics({
    period,
    trackId,
    mentorFilter,
    access,
    learningStatuses,
  });

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={2}>Аналитика по собеседованиям</Title>
          <Text c="dimmed" size="sm">
            Метрики учитывают выбранных выше учеников и направление.
          </Text>
        </div>
        <SegmentedControl
          value={period}
          onChange={(value) => onPeriodChange(value as MentorAnalyticsPeriod)}
          data={Object.entries(periodLabels).map(([value, label]) => ({
            value,
            label,
          }))}
        />
      </Group>

      {query.isPending ? (
        <LoadingState label="Собираем аналитику…" />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <>
          <SimpleGrid cols={{ base: 1, xs: 2, md: 4 }}>
            <MetricCard
              label="Собеседований"
              value={query.data.total_interviews}
              hint={`${query.data.students_with_interviews} из ${query.data.selected_student_count} учеников были на интервью`}
            />
            <MetricCard
              label="Офферов получено"
              value={query.data.offers_received}
              color="green"
              hint={`Конверсия треков в оффер — ${query.data.offer_conversion_percent}%`}
            />
            <MetricCard
              label="AI-разборов запущено"
              value={query.data.ai_analyses_started}
              hint={`${query.data.ai_analyses_ready} готовы · ${query.data.ai_analyses_failed} с ошибкой`}
            />
            <MetricCard
              label="Активных треков"
              value={query.data.active_processes}
              hint={`${query.data.upcoming_interviews_next_week} этапов запланировано на ближайшие 7 дней`}
            />
          </SimpleGrid>

          <SimpleGrid cols={{ base: 1, lg: 2 }}>
            <Card withBorder>
              <Stack>
                <div>
                  <Title order={3}>Этапы собеседований</Title>
                  <Text size="sm" c="dimmed">
                    {periodLabels[period]} · {query.data.unique_companies}{" "}
                    компаний
                  </Text>
                </div>
                <SimpleGrid cols={{ base: 1, xs: 2 }}>
                  {query.data.stage_counts.map((stage) => (
                    <Group key={stage.stage_type} justify="space-between">
                      <Text size="sm">{stageLabels[stage.stage_type]}</Text>
                      <Badge variant="light" size="lg">
                        {stage.count}
                      </Badge>
                    </Group>
                  ))}
                </SimpleGrid>
              </Stack>
            </Card>

            <Card withBorder>
              <Stack>
                <div>
                  <Title order={3}>Качество данных и охват</Title>
                  <Text size="sm" c="dimmed">
                    Помогает увидеть, где ученикам нужна дополнительная
                    поддержка.
                  </Text>
                </div>
                <RateRow
                  label="Собеседования с записью"
                  value={query.data.recording_coverage_percent}
                  description={`${query.data.interviews_with_recording} записей можно разобрать повторно`}
                />
                <RateRow
                  label="Успешность AI-разборов"
                  value={query.data.ai_success_rate_percent}
                  description="Доля успешно завершённых среди готовых и завершившихся ошибкой"
                />
                <Group justify="space-between">
                  <Text size="sm">В среднем на активного участника</Text>
                  <Text fw={700}>
                    {query.data.average_interviews_per_participant} интервью
                  </Text>
                </Group>
                <Group justify="space-between">
                  <Text size="sm">Без собеседований за период</Text>
                  <Badge
                    color={
                      query.data.students_without_interviews > 0
                        ? "orange"
                        : "green"
                    }
                    variant="light"
                  >
                    {query.data.students_without_interviews}
                  </Badge>
                </Group>
                <Group justify="space-between">
                  <Text size="sm">Сейчас в статусе «собеседования»</Text>
                  <Badge variant="light">
                    {query.data.current_interviewing_students}
                  </Badge>
                </Group>
              </Stack>
            </Card>
          </SimpleGrid>

          <Card withBorder p={0}>
            <Stack gap={0}>
              <div style={{ padding: "var(--mantine-spacing-lg)" }}>
                <Title order={3}>Рейтинг активности</Title>
                <Text size="sm" c="dimmed">
                  По количеству пройденных этапов за выбранный период.
                </Text>
              </div>
              {query.data.ranking.length === 0 ? (
                <Text c="dimmed" p="lg" pt={0}>
                  За выбранный период собеседований не было.
                </Text>
              ) : (
                <Table.ScrollContainer minWidth={850}>
                  <Table verticalSpacing="sm" highlightOnHover>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Место</Table.Th>
                        <Table.Th>Ученик</Table.Th>
                        <Table.Th>Этапов</Table.Th>
                        <Table.Th>Компаний</Table.Th>
                        <Table.Th>Офферов</Table.Th>
                        <Table.Th>AI-разборов</Table.Th>
                        <Table.Th>Последнее интервью</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {query.data.ranking.map((student) => (
                        <Table.Tr key={student.student_id}>
                          <Table.Td>
                            <Badge
                              color={student.position <= 3 ? "blue" : "gray"}
                              variant={
                                student.position <= 3 ? "filled" : "light"
                              }
                            >
                              #{student.position}
                            </Badge>
                          </Table.Td>
                          <Table.Td>
                            <Stack gap={2}>
                              <Anchor
                                component={Link}
                                to={`/mentor/students/${student.student_id}`}
                                fw={700}
                              >
                                {personName(
                                  student.first_name,
                                  student.last_name,
                                )}
                              </Anchor>
                              <TelegramChatLink
                                username={student.telegram_username}
                              />
                            </Stack>
                          </Table.Td>
                          <Table.Td fw={700}>
                            {student.interview_count}
                          </Table.Td>
                          <Table.Td>{student.company_count}</Table.Td>
                          <Table.Td>{student.offer_count}</Table.Td>
                          <Table.Td>{student.ai_analysis_count}</Table.Td>
                          <Table.Td>
                            {formatDate(student.last_interview_at)}
                          </Table.Td>
                        </Table.Tr>
                      ))}
                    </Table.Tbody>
                  </Table>
                </Table.ScrollContainer>
              )}
            </Stack>
          </Card>
        </>
      )}
    </Stack>
  );
}
