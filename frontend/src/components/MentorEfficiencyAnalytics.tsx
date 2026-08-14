import {
  Alert,
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

import { useMentorEfficiencyAnalytics } from "../features/mentor/queries";
import type { MentorAnalyticsPeriod, StudentAccessFilter } from "../types/api";
import { ErrorState } from "./ErrorState";
import { LoadingState } from "./LoadingState";
import { TelegramChatLink } from "./TelegramChatLink";

const periodLabels: Record<MentorAnalyticsPeriod, string> = {
  week: "Последние 7 дней",
  month: "Последние 30 дней",
  all: "Всё время",
};

function personName(firstName: string, lastName: string | null): string {
  return [firstName, lastName].filter(Boolean).join(" ");
}

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleDateString("ru-RU") : "—";
}

function rateColor(value: number, hasStudents: boolean): string {
  if (!hasStudents) return "gray";
  if (value >= 70) return "green";
  if (value >= 40) return "yellow";
  return "red";
}

function MetricCard({
  label,
  value,
  hint,
  color,
}: {
  label: string;
  value: number;
  hint: string;
  color?: string;
}) {
  return (
    <Card withBorder>
      <Stack gap={6}>
        <Text className="technical-label">{label}</Text>
        <Title order={2} c={color}>
          {value}
        </Title>
        <Text size="xs" c="dimmed">
          {hint}
        </Text>
      </Stack>
    </Card>
  );
}

export function MentorEfficiencyAnalytics({
  period,
  onPeriodChange,
  trackId,
  access,
}: {
  period: MentorAnalyticsPeriod;
  onPeriodChange: (period: MentorAnalyticsPeriod) => void;
  trackId: string | null;
  access: StudentAccessFilter;
}) {
  const query = useMentorEfficiencyAnalytics({ period, trackId, access });

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <div>
          <Title order={2}>Эффективность менторов</Title>
          <Text c="dimmed" size="sm" maw={760}>
            Реальная активность считается по состоявшимся этапам, а не только по
            статусу ученика. Так видно, где воронка движется, а где нужна
            помощь.
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
        <LoadingState label="Считаем эффективность менторов…" />
      ) : query.isError ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <>
          <SimpleGrid cols={{ base: 1, xs: 2, lg: 4 }}>
            <MetricCard
              label="Менторов с учениками"
              value={query.data.mentor_count}
              hint={`${query.data.assigned_students} учеников распределено`}
            />
            <MetricCard
              label="На собеседованиях"
              value={query.data.interviewing_students}
              hint="Текущий статус учеников"
            />
            <MetricCard
              label="Реально активны"
              value={query.data.active_interviewing_students}
              hint={`Был этап за период: ${periodLabels[period].toLowerCase()}`}
              color="green"
            />
            <MetricCard
              label="Требуют внимания"
              value={query.data.inactive_interviewing_students}
              hint="Статус есть, но этапов за период нет"
              color={
                query.data.inactive_interviewing_students > 0
                  ? "orange"
                  : "green"
              }
            />
          </SimpleGrid>

          {query.data.unassigned_students > 0 && (
            <Alert color="orange" title="Ученики без ментора">
              Без ментора сейчас {query.data.unassigned_students}; из них в
              статусе «ходит на собеседования» —{" "}
              {query.data.unassigned_interviewing_students}.
            </Alert>
          )}

          <Card withBorder p={0}>
            <Stack gap={0}>
              <div style={{ padding: "var(--mantine-spacing-lg)" }}>
                <Title order={3}>Состояние учеников по менторам</Title>
                <Text size="sm" c="dimmed">
                  Процент активности — доля учеников со статусом «ходит на
                  собеседования», у которых был хотя бы один этап за период.
                  Покрытие записями считается среди реально активных.
                </Text>
              </div>
              {query.data.mentors.length === 0 ? (
                <Text c="dimmed" p="lg" pt={0}>
                  Для выбранных фильтров назначенных учеников нет.
                </Text>
              ) : (
                <Table.ScrollContainer minWidth={1380}>
                  <Table verticalSpacing="sm" highlightOnHover stickyHeader>
                    <Table.Thead>
                      <Table.Tr>
                        <Table.Th>Ментор</Table.Th>
                        <Table.Th>Ученики</Table.Th>
                        <Table.Th>На собеседованиях</Table.Th>
                        <Table.Th>Реально активны</Table.Th>
                        <Table.Th>Выкладывают записи</Table.Th>
                        <Table.Th>Этапов</Table.Th>
                        <Table.Th>AI-разборов</Table.Th>
                        <Table.Th>Офферов</Table.Th>
                        <Table.Th>Ближайшие 7 дней</Table.Th>
                        <Table.Th>Требуют внимания</Table.Th>
                        <Table.Th>Последний этап</Table.Th>
                      </Table.Tr>
                    </Table.Thead>
                    <Table.Tbody>
                      {query.data.mentors.map((mentor) => {
                        const participationColor = rateColor(
                          mentor.participation_percent,
                          mentor.interviewing_students > 0,
                        );
                        const recordingColor = rateColor(
                          mentor.recording_participation_percent,
                          mentor.active_interviewing_students > 0,
                        );
                        return (
                          <Table.Tr key={mentor.mentor_id}>
                            <Table.Td>
                              <Stack gap={3}>
                                <Group gap="xs" wrap="nowrap">
                                  <Text fw={700}>
                                    {personName(
                                      mentor.first_name,
                                      mentor.last_name,
                                    )}
                                  </Text>
                                  {mentor.role === "admin" && (
                                    <Badge size="xs" variant="light">
                                      Админ
                                    </Badge>
                                  )}
                                </Group>
                                <TelegramChatLink
                                  username={mentor.telegram_username}
                                />
                              </Stack>
                            </Table.Td>
                            <Table.Td fw={700}>
                              {mentor.assigned_students}
                            </Table.Td>
                            <Table.Td>{mentor.interviewing_students}</Table.Td>
                            <Table.Td>
                              <Stack gap={5} miw={140}>
                                <Group justify="space-between" gap="xs">
                                  <Text size="sm" fw={700}>
                                    {mentor.active_interviewing_students} из{" "}
                                    {mentor.interviewing_students}
                                  </Text>
                                  <Badge
                                    color={participationColor}
                                    variant="light"
                                  >
                                    {mentor.participation_percent}%
                                  </Badge>
                                </Group>
                                <Progress
                                  value={mentor.participation_percent}
                                  color={participationColor}
                                  size="xs"
                                />
                              </Stack>
                            </Table.Td>
                            <Table.Td>
                              <Stack gap={5} miw={140}>
                                <Group justify="space-between" gap="xs">
                                  <Text size="sm" fw={700}>
                                    {mentor.recording_students} учеников
                                  </Text>
                                  <Badge color={recordingColor} variant="light">
                                    {mentor.recording_participation_percent}%
                                  </Badge>
                                </Group>
                                <Text size="xs" c="dimmed">
                                  {mentor.recording_count} записей
                                </Text>
                              </Stack>
                            </Table.Td>
                            <Table.Td>
                              <Text fw={700}>{mentor.interview_count}</Text>
                              <Text size="xs" c="dimmed">
                                {mentor.average_interviews_per_active_student}{" "}
                                на активного
                              </Text>
                            </Table.Td>
                            <Table.Td>{mentor.ai_analysis_count}</Table.Td>
                            <Table.Td>{mentor.offer_count}</Table.Td>
                            <Table.Td>{mentor.upcoming_students}</Table.Td>
                            <Table.Td>
                              <Badge
                                color={
                                  mentor.inactive_interviewing_students > 0
                                    ? "orange"
                                    : "green"
                                }
                                variant="light"
                              >
                                {mentor.inactive_interviewing_students}
                              </Badge>
                            </Table.Td>
                            <Table.Td>
                              {formatDate(mentor.last_interview_at)}
                            </Table.Td>
                          </Table.Tr>
                        );
                      })}
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
