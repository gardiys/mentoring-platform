import {
  Badge,
  Button,
  Card,
  Group,
  MultiSelect,
  Pagination,
  Select,
  Stack,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useAdminStudents } from "../features/admin/studentQueries";
import type { StudentAccessFilter, StudentLearningStatus } from "../types/api";
import {
  ADMIN_STUDENTS_FILTERS_STORAGE_KEY,
  readStoredStudentListFilters,
  storeStudentListFilters,
} from "../utils/studentListFilters";

const PAGE_SIZE = 50;

const statusLabels: Record<StudentLearningStatus, string> = {
  learning: "Учится",
  interviewing: "Ходит на собеседования",
  probation: "Работает на испыталке",
  finished: "Обучение завершено",
};

function studentName(firstName: string, lastName: string | null) {
  return [firstName, lastName].filter(Boolean).join(" ");
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString("ru-RU") : "—";
}

export function AdminStudentsPage() {
  const [initialFilters] = useState(() =>
    readStoredStudentListFilters(ADMIN_STUDENTS_FILTERS_STORAGE_KEY),
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
  const [page, setPage] = useState(1);
  const query = useAdminStudents({
    query: debouncedSearch,
    trackId,
    learningStatuses: statuses,
    access,
    mentorFilter,
    page,
  });

  useEffect(
    () => setPage(1),
    [debouncedSearch, trackId, statuses, access, mentorFilter],
  );

  useEffect(() => {
    storeStudentListFilters(ADMIN_STUDENTS_FILTERS_STORAGE_KEY, {
      search,
      trackId,
      statuses,
      access,
      mentorFilter,
      sort: initialFilters.sort,
    });
  }, [search, trackId, statuses, access, mentorFilter, initialFilters.sort]);

  useEffect(() => {
    if (!query.data) return;
    if (trackId && !query.data.tracks.some((track) => track.id === trackId)) {
      setTrackId(null);
    }
    if (
      mentorFilter !== "all" &&
      mentorFilter !== "unassigned" &&
      !query.data.mentors.some((mentor) => mentor.id === mentorFilter)
    ) {
      setMentorFilter("all");
    }
  }, [mentorFilter, query.data, trackId]);

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Админ-панель · Ученики"
          title="Ученики"
          description="Личные данные, учебные треки и доступ к платформе в одном месте."
        />
        <Button component={Link} to="/admin/students/new">
          + Добавить ученика
        </Button>
      </Group>

      <Card withBorder>
        <Stack>
          <Group grow align="flex-end">
            <TextInput
              label="Поиск"
              placeholder="Имя, email, username или Telegram ID"
              value={search}
              onChange={(event) => setSearch(event.currentTarget.value)}
            />
            <Select
              label="Направление"
              placeholder="Все направления"
              clearable
              searchable
              value={trackId}
              onChange={setTrackId}
              data={(query.data?.tracks ?? []).map((track) => ({
                value: track.id,
                label: track.title,
              }))}
            />
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
            <Select
              label="Доступ"
              value={access}
              data={[
                { value: "active", label: "Доступ открыт" },
                { value: "blocked", label: "Доступ закрыт" },
                { value: "all", label: "Любой доступ" },
              ]}
              onChange={(value) =>
                setAccess((value as StudentAccessFilter | null) ?? "active")
              }
            />
            <Select
              label="Ментор"
              value={mentorFilter}
              onChange={(value) => setMentorFilter(value ?? "all")}
              searchable
              data={[
                { value: "all", label: "Все менторы" },
                { value: "unassigned", label: "Без ментора" },
                ...(query.data?.mentors ?? []).map((mentor) => ({
                  value: mentor.id,
                  label: `${studentName(mentor.first_name, mentor.last_name)}${mentor.role === "admin" ? " · администратор" : ""}`,
                })),
              ]}
            />
          </Group>

          {query.isPending ? (
            <LoadingState label="Загружаем учеников…" />
          ) : query.isError ? (
            <ErrorState
              error={query.error}
              retry={() => void query.refetch()}
            />
          ) : (
            <>
              <Text fw={600}>Найдено учеников: {query.data.total}</Text>
              <Table.ScrollContainer minWidth={900}>
                <Table striped highlightOnHover verticalSpacing="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Ученик</Table.Th>
                      <Table.Th>Контакты</Table.Th>
                      <Table.Th>Треки</Table.Th>
                      <Table.Th>Ментор</Table.Th>
                      <Table.Th>Текущий статус</Table.Th>
                      <Table.Th>Последний прогресс</Table.Th>
                      <Table.Th>Доступ</Table.Th>
                      <Table.Th />
                    </Table.Tr>
                  </Table.Thead>
                  <Table.Tbody>
                    {query.data.items.map((student) => (
                      <Table.Tr key={student.id}>
                        <Table.Td>
                          <Text fw={600}>
                            {studentName(student.first_name, student.last_name)}
                          </Text>
                          <Text size="xs" c="dimmed">
                            Добавлен {formatDate(student.created_at)}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">
                            {student.email ?? "Email не указан"}
                          </Text>
                          <Text size="xs" c="dimmed">
                            {student.telegram_username
                              ? `@${student.telegram_username}`
                              : student.telegram_id
                                ? `Telegram ID: ${student.telegram_id}`
                                : "Telegram не указан"}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Group gap={6}>
                            {student.tracks.length > 0 ? (
                              student.tracks.map((track) => (
                                <Badge key={track.id} variant="light">
                                  {track.title}
                                </Badge>
                              ))
                            ) : (
                              <Text size="sm" c="dimmed">
                                Не назначены
                              </Text>
                            )}
                          </Group>
                        </Table.Td>
                        <Table.Td>
                          {student.mentor ? (
                            <Text size="sm" fw={500}>
                              {`${studentName(
                                student.mentor.first_name,
                                student.mentor.last_name,
                              )}${student.mentor.role === "admin" ? " · администратор" : ""}`}
                            </Text>
                          ) : (
                            <Text size="sm" c="dimmed">
                              Не назначен
                            </Text>
                          )}
                        </Table.Td>
                        <Table.Td>
                          <Badge variant="light">
                            {statusLabels[student.learning_status]}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Text size="sm">
                            {student.last_progress_at
                              ? formatDate(student.last_progress_at)
                              : "Нет отметок"}
                          </Text>
                        </Table.Td>
                        <Table.Td>
                          <Badge
                            color={student.is_active ? "green" : "red"}
                            variant="light"
                          >
                            {student.is_active ? "Открыт" : "Закрыт"}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          <Button
                            component={Link}
                            to={`/admin/students/${student.id}/edit`}
                            variant="subtle"
                            size="xs"
                          >
                            Редактировать
                          </Button>
                        </Table.Td>
                      </Table.Tr>
                    ))}
                  </Table.Tbody>
                </Table>
              </Table.ScrollContainer>
              {query.data.total === 0 && (
                <Text c="dimmed">Ученики не найдены.</Text>
              )}
              {query.data.total > PAGE_SIZE && (
                <Pagination
                  value={page}
                  onChange={setPage}
                  total={Math.ceil(query.data.total / PAGE_SIZE)}
                />
              )}
            </>
          )}
        </Stack>
      </Card>
    </Stack>
  );
}
