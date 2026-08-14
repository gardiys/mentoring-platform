import {
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  MultiSelect,
  Pagination,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Tabs,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { MentorInterviewAnalytics } from "../components/MentorInterviewAnalytics";
import { MentorEfficiencyAnalytics } from "../components/MentorEfficiencyAnalytics";
import { PageHeader } from "../components/PageHeader";
import { ProgressBar } from "../components/ProgressBar";
import { TelegramChatLink } from "../components/TelegramChatLink";
import {
  useMentorStudents,
  useUpdateMentorStudentState,
} from "../features/mentor/queries";
import type {
  MentorStudentActivityKind,
  MentorAnalyticsPeriod,
  MentorStudentSort,
  StudentAccessFilter,
  StudentLearningStatus,
  StudentStrengthLevel,
} from "../types/api";
import {
  readStoredStudentListFilters,
  storeStudentListFilters,
  STUDENT_PROGRESS_FILTERS_STORAGE_KEY,
} from "../utils/studentListFilters";

const statusLabels: Record<StudentLearningStatus, string> = {
  learning: "Учится",
  interviewing: "Ходит на собеседования",
  probation: "Работает на испыталке",
  finished: "Обучение завершено",
};

const levelLabels = {
  weak: "Слабый",
  medium: "Средний",
  strong: "Сильный",
} as const;

const activityLabels: Record<MentorStudentActivityKind, string> = {
  roadmap: "Роадмап",
  interview: "Собеседования",
  interview_cards: "Карточки",
};

const sortOptions: Array<{ value: MentorStudentSort; label: string }> = [
  { value: "name_asc", label: "По имени" },
  { value: "learning_start_desc", label: "Старт обучения: новые сначала" },
  { value: "learning_start_asc", label: "Старт обучения: ранние сначала" },
  { value: "last_activity_desc", label: "Последняя активность: недавние" },
  { value: "last_activity_asc", label: "Последняя активность: давно не было" },
];

function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleDateString("ru-RU") : "Не указана";
}

function formatActivity(value: string | null): string {
  if (!value) return "Активности пока не было";
  const activityAt = new Date(value);
  const days = Math.max(
    0,
    Math.floor((Date.now() - activityAt.getTime()) / (24 * 60 * 60 * 1000)),
  );
  if (days === 0) return "Сегодня";
  if (days === 1) return "Вчера";
  return `${days} дн. назад`;
}

function personName(firstName: string, lastName: string | null): string {
  return [firstName, lastName].filter(Boolean).join(" ");
}

function InlineStudentStatus({
  studentId,
  value,
  strengthLevel,
  studentName,
}: {
  studentId: string;
  value: StudentLearningStatus;
  strengthLevel: StudentStrengthLevel | null;
  studentName: string;
}) {
  const update = useUpdateMentorStudentState(studentId);
  const [selectedStatus, setSelectedStatus] = useState(value);

  useEffect(() => setSelectedStatus(value), [value]);

  return (
    <Select
      aria-label={`Статус ученика ${studentName}`}
      data={Object.entries(statusLabels).map(([status, label]) => ({
        value: status,
        label,
      }))}
      value={selectedStatus}
      allowDeselect={false}
      size="xs"
      miw={190}
      disabled={update.isPending}
      onChange={(nextValue) => {
        if (!nextValue || nextValue === selectedStatus) return;
        const previousStatus = selectedStatus;
        const nextStatus = nextValue as StudentLearningStatus;
        setSelectedStatus(nextStatus);
        update.mutate(
          { learningStatus: nextStatus, strengthLevel },
          {
            onSuccess: () =>
              notifications.show({
                color: "green",
                message: `Статус ученика ${studentName} обновлён`,
              }),
            onError: (error) => {
              setSelectedStatus(previousStatus);
              notifications.show({ color: "red", message: error.message });
            },
          },
        );
      }}
    />
  );
}

export function MentorStudentsPage() {
  const [initialFilters] = useState(() =>
    readStoredStudentListFilters(STUDENT_PROGRESS_FILTERS_STORAGE_KEY),
  );
  const [search, setSearch] = useState(initialFilters.search);
  const [debouncedSearch] = useDebouncedValue(search.trim(), 250);
  const [trackId, setTrackId] = useState<string | null>(initialFilters.trackId);
  const [statuses, setStatuses] = useState<StudentLearningStatus[]>(
    initialFilters.statuses,
  );
  const [access, setAccess] = useState<StudentAccessFilter>(
    initialFilters.access,
  );
  const [mentorFilter, setMentorFilter] = useState(initialFilters.mentorFilter);
  const [sort, setSort] = useState<MentorStudentSort>(initialFilters.sort);
  const [view, setView] = useState<
    "students" | "analytics" | "mentor-efficiency"
  >("students");
  const [analyticsPeriod, setAnalyticsPeriod] =
    useState<MentorAnalyticsPeriod>("week");
  const [page, setPage] = useState(1);
  const query = useMentorStudents({
    query: debouncedSearch,
    trackId,
    mentorFilter,
    access,
    learningStatuses: statuses,
    sort,
    page,
  });

  useEffect(
    () => setPage(1),
    [debouncedSearch, trackId, statuses, access, mentorFilter, sort],
  );

  useEffect(() => {
    storeStudentListFilters(STUDENT_PROGRESS_FILTERS_STORAGE_KEY, {
      search,
      trackId,
      statuses,
      access,
      mentorFilter,
      sort,
    });
  }, [search, trackId, statuses, access, mentorFilter, sort]);

  useEffect(() => {
    if (!query.data) return;
    if (
      trackId &&
      !query.data.directions.some((direction) => direction.id === trackId)
    ) {
      setTrackId(null);
    }
    if (
      mentorFilter !== "all" &&
      (!query.data.can_filter_by_mentor ||
        (mentorFilter !== "unassigned" &&
          !query.data.mentors.some((mentor) => mentor.id === mentorFilter)))
    ) {
      setMentorFilter("all");
    }
  }, [mentorFilter, query.data, trackId]);

  if (query.isPending) return <LoadingState label="Загружаем учеников…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Менторская · текущая неделя"
        title="Мои ученики"
        description="Текущие темы, сроки, активность, собеседования и состояние каждого ученика."
      />
      <Tabs
        value={view}
        onChange={(value) =>
          setView(
            (value as "students" | "analytics" | "mentor-efficiency" | null) ??
              "students",
          )
        }
      >
        <Tabs.List>
          <Tabs.Tab value="students">Ученики</Tabs.Tab>
          <Tabs.Tab value="analytics">Аналитика собеседований</Tabs.Tab>
          {query.data.can_filter_by_mentor && (
            <Tabs.Tab value="mentor-efficiency">
              Эффективность менторов
            </Tabs.Tab>
          )}
        </Tabs.List>
      </Tabs>
      <Card withBorder>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} verticalSpacing="sm">
          {view === "students" && (
            <TextInput
              label="Поиск"
              placeholder="Имя, email или Telegram"
              value={search}
              onChange={(event) => setSearch(event.currentTarget.value)}
            />
          )}
          <Select
            label="Направление"
            placeholder="Python и Go"
            clearable
            searchable
            value={trackId}
            onChange={setTrackId}
            data={query.data.directions.map((direction) => ({
              value: direction.id,
              label: direction.title,
            }))}
          />
          {view !== "mentor-efficiency" && (
            <MultiSelect
              label="Текущий статус"
              placeholder="Все статусы"
              clearable
              value={statuses}
              onChange={(values) =>
                setStatuses(values as StudentLearningStatus[])
              }
              data={Object.entries(statusLabels).map(([value, label]) => ({
                value,
                label,
              }))}
            />
          )}
          <Select
            label="Доступ"
            value={access}
            onChange={(value) =>
              setAccess((value as StudentAccessFilter | null) ?? "active")
            }
            data={[
              { value: "active", label: "Доступ открыт" },
              { value: "blocked", label: "Доступ закрыт" },
              { value: "all", label: "Любой доступ" },
            ]}
          />
          {query.data.can_filter_by_mentor && view !== "mentor-efficiency" && (
            <Select
              label="Ментор"
              value={mentorFilter}
              onChange={(value) => setMentorFilter(value ?? "all")}
              searchable
              data={[
                { value: "all", label: "Все менторы" },
                { value: "unassigned", label: "Без ментора" },
                ...query.data.mentors.map((mentor) => ({
                  value: mentor.id,
                  label: `${personName(mentor.first_name, mentor.last_name)}${mentor.role === "admin" ? " · администратор" : ""}`,
                })),
              ]}
            />
          )}
          {view === "students" && (
            <Select
              label="Сортировка"
              value={sort}
              onChange={(value) =>
                setSort((value as MentorStudentSort | null) ?? "name_asc")
              }
              data={sortOptions}
            />
          )}
        </SimpleGrid>
      </Card>
      {view === "analytics" ? (
        <MentorInterviewAnalytics
          period={analyticsPeriod}
          onPeriodChange={setAnalyticsPeriod}
          trackId={trackId}
          mentorFilter={mentorFilter}
          access={access}
          learningStatuses={statuses}
        />
      ) : view === "mentor-efficiency" ? (
        <MentorEfficiencyAnalytics
          period={analyticsPeriod}
          onPeriodChange={setAnalyticsPeriod}
          trackId={trackId}
          access={access}
        />
      ) : (
        <>
          <Group justify="space-between">
            <Text fw={600}>Найдено учеников: {query.data.total}</Text>
            <Text size="sm" c="dimmed">
              Красным отмечены ученики, которые не укладываются в сроки
            </Text>
          </Group>
          {query.data.items.length === 0 ? (
            <Text c="dimmed">Подходящих учеников нет.</Text>
          ) : (
            <Card withBorder p={0}>
              <Table.ScrollContainer minWidth={1380}>
                <Table verticalSpacing="md" highlightOnHover stickyHeader>
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Ученик</Table.Th>
                      <Table.Th>Статус</Table.Th>
                      <Table.Th>Текущий фокус</Table.Th>
                      <Table.Th>Прогресс</Table.Th>
                      <Table.Th>За неделю</Table.Th>
                      <Table.Th>Последняя активность</Table.Th>
                      <Table.Th>Старт обучения</Table.Th>
                      <Table.Th aria-label="Действия" />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {query.data.items.map((student) => (
                      <Table.Tr
                        key={student.id}
                        className={
                          student.is_overdue
                            ? "student-progress-row student-progress-row--overdue"
                            : "student-progress-row"
                        }
                      >
                        <Table.Td>
                          <Stack gap={4} miw={190}>
                            <Anchor
                              component={Link}
                              to={`/mentor/students/${student.id}`}
                              fw={700}
                            >
                              {personName(
                                student.first_name,
                                student.last_name,
                              )}
                            </Anchor>
                            <Text c="dimmed" size="xs">
                              {student.email ?? "Email не указан"}
                            </Text>
                            <TelegramChatLink
                              username={student.telegram_username}
                            />
                          </Stack>
                        </Table.Td>
                        <Table.Td>
                          <Stack gap={6} align="flex-start" miw={170}>
                            <Badge
                              color={student.is_active ? "green" : "red"}
                              variant="outline"
                              size="sm"
                            >
                              {student.is_active
                                ? "Доступ открыт"
                                : "Доступ закрыт"}
                            </Badge>
                            {student.is_overdue && (
                              <Badge color="red">Не в срок</Badge>
                            )}
                            <InlineStudentStatus
                              studentId={student.id}
                              value={student.learning_status}
                              strengthLevel={student.strength_level}
                              studentName={personName(
                                student.first_name,
                                student.last_name,
                              )}
                            />
                            {student.strength_level && (
                              <Badge color="gray" variant="outline" size="sm">
                                {levelLabels[student.strength_level]}
                              </Badge>
                            )}
                          </Stack>
                        </Table.Td>
                        <Table.Td>
                          <Stack gap={6} miw={230}>
                            {student.current_topics.length > 0 ? (
                              student.current_topics.map((topic) => (
                                <Group
                                  key={topic.id}
                                  justify="space-between"
                                  wrap="nowrap"
                                >
                                  <div className="min-width-zero">
                                    <Text size="sm" fw={600}>
                                      {topic.title}
                                    </Text>
                                    <Text size="xs" c="dimmed" lineClamp={1}>
                                      {topic.roadmap_title}
                                    </Text>
                                  </div>
                                  <Badge
                                    color={topic.is_overdue ? "red" : "blue"}
                                    variant="light"
                                  >
                                    {topic.days_in_topic === 0
                                      ? "сегодня"
                                      : `${topic.days_in_topic} дн.`}
                                  </Badge>
                                </Group>
                              ))
                            ) : student.learning_status === "interviewing" ? (
                              <Text size="sm" fw={600}>
                                Проходит собеседования
                              </Text>
                            ) : (
                              <Text size="sm" c="dimmed">
                                Активная тема не отмечена
                              </Text>
                            )}
                          </Stack>
                        </Table.Td>
                        <Table.Td>
                          <Stack gap="sm" miw={220}>
                            {student.roadmaps.map((roadmap) => (
                              <div key={roadmap.id}>
                                <Group justify="space-between" mb={4}>
                                  <Text size="xs" fw={600} lineClamp={1}>
                                    {roadmap.title}
                                  </Text>
                                  {roadmap.overdue_sections > 0 && (
                                    <Badge
                                      size="xs"
                                      color="red"
                                      variant="light"
                                    >
                                      {roadmap.overdue_sections} просрочено
                                    </Badge>
                                  )}
                                </Group>
                                <ProgressBar
                                  completed={roadmap.completed_topics}
                                  total={roadmap.total_topics}
                                  percent={roadmap.progress_percent}
                                />
                              </div>
                            ))}
                            {student.roadmaps.length === 0 && (
                              <Text size="sm" c="dimmed">
                                Роадмап не назначен
                              </Text>
                            )}
                          </Stack>
                        </Table.Td>
                        <Table.Td>
                          <Stack gap={4} miw={120}>
                            <Text size="sm" fw={600}>
                              {student.completed_topics_this_week} тем
                            </Text>
                            <Text size="xs" c="dimmed">
                              Моков: {student.mock_interview_count}
                            </Text>
                          </Stack>
                        </Table.Td>
                        <Table.Td>
                          <Stack gap={4} miw={150}>
                            <Text size="sm" fw={600}>
                              {formatActivity(student.last_progress_at)}
                            </Text>
                            <Text size="xs" c="dimmed">
                              {student.last_activity_kind
                                ? activityLabels[student.last_activity_kind]
                                : "Нет данных"}
                              {student.last_progress_at
                                ? ` · ${new Date(student.last_progress_at).toLocaleString("ru-RU")}`
                                : ""}
                            </Text>
                          </Stack>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm" miw={100}>
                            {formatDate(student.learning_start_date)}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Button
                            component={Link}
                            to={`/mentor/students/${student.id}`}
                            variant="light"
                            size="xs"
                            miw={96}
                          >
                            Открыть
                          </Button>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
            </Card>
          )}
          {query.data.total > query.data.limit && (
            <Pagination
              value={page}
              onChange={setPage}
              total={Math.ceil(query.data.total / query.data.limit)}
              mx="auto"
            />
          )}
        </>
      )}
    </Stack>
  );
}
