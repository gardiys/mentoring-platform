import {
  Badge,
  Button,
  Card,
  Group,
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
import {
  type StudentAccessFilter,
  useAdminStudents,
} from "../features/admin/studentQueries";

const PAGE_SIZE = 50;

function studentName(firstName: string, lastName: string | null) {
  return [firstName, lastName].filter(Boolean).join(" ");
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleDateString("ru-RU") : "—";
}

export function AdminStudentsPage() {
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search.trim(), 250);
  const [access, setAccess] = useState<StudentAccessFilter>("all");
  const [page, setPage] = useState(1);
  const query = useAdminStudents({ query: debouncedSearch, access, page });

  useEffect(() => setPage(1), [debouncedSearch, access]);

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
              placeholder="Имя, email или Telegram ID"
              value={search}
              onChange={(event) => setSearch(event.currentTarget.value)}
            />
            <Select
              label="Доступ"
              value={access}
              data={[
                { value: "all", label: "Все ученики" },
                { value: "active", label: "Доступ открыт" },
                { value: "blocked", label: "Доступ закрыт" },
              ]}
              onChange={(value) =>
                setAccess((value as StudentAccessFilter | null) ?? "all")
              }
            />
          </Group>

          {query.isPending ? (
            <LoadingState label="Загружаем учеников…" />
          ) : query.isError ? (
            <ErrorState retry={() => void query.refetch()} />
          ) : (
            <>
              <Table.ScrollContainer minWidth={900}>
                <Table striped highlightOnHover verticalSpacing="sm">
                  <Table.Thead>
                    <Table.Tr>
                      <Table.Th>Ученик</Table.Th>
                      <Table.Th>Контакты</Table.Th>
                      <Table.Th>Треки</Table.Th>
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
                            {student.telegram_id
                              ? `Telegram ID: ${student.telegram_id}`
                              : "Telegram ID не указан"}
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
