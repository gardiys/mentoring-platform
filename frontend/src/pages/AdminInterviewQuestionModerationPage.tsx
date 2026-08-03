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
import { useState } from "react";
import { Link } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useAdminQuestionModeration } from "../features/interviews/intelligenceQueries";

type QueueStatus =
  "needs_review" | "mentor_approved" | "approved" | "rejected" | "all";

const statusLabels = {
  pending: "Ожидает проверки",
  mentor_approved: "Рекомендован ментором",
  approved: "Добавлен",
  rejected: "Отклонён",
} as const;

export function AdminInterviewQuestionModerationPage() {
  const [status, setStatus] = useState<QueueStatus>("needs_review");
  const [search, setSearch] = useState("");
  const [debouncedSearch] = useDebouncedValue(search, 300);
  const [page, setPage] = useState(1);
  const offset = (page - 1) * 20;
  const query = useAdminQuestionModeration(status, debouncedSearch, offset);

  if (query.isPending) return <LoadingState label="Загружаем вопросы…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  const pages = Math.max(1, Math.ceil(query.data.total / query.data.limit));
  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Администрирование · Собеседования"
        title="Вопросы для карточек"
        description="Проверяйте извлечённые вопросы. Совпадения дополняют существующую карточку компанией и статистикой появлений."
      />
      <Group align="flex-end" grow>
        <TextInput
          label="Поиск"
          placeholder="Вопрос, тема или компания"
          value={search}
          onChange={(event) => {
            setSearch(event.currentTarget.value);
            setPage(1);
          }}
        />
        <Select
          label="Статус"
          value={status}
          data={[
            { value: "needs_review", label: "Требуют решения" },
            { value: "mentor_approved", label: "Рекомендованы ментором" },
            { value: "approved", label: "Добавлены" },
            { value: "rejected", label: "Отклонены" },
            { value: "all", label: "Все" },
          ]}
          onChange={(value) => {
            setStatus((value as QueueStatus | null) ?? "needs_review");
            setPage(1);
          }}
        />
      </Group>
      {query.data.items.length === 0 ? (
        <Card withBorder>
          <Text c="dimmed">В этой очереди пока нет вопросов.</Text>
        </Card>
      ) : (
        <Card withBorder p={0}>
          <Table.ScrollContainer minWidth={850}>
            <Table verticalSpacing="sm" horizontalSpacing="md">
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Вопрос</Table.Th>
                  <Table.Th>Направление</Table.Th>
                  <Table.Th>Компания</Table.Th>
                  <Table.Th>Статус</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {query.data.items.map((item) => (
                  <Table.Tr key={item.question_id}>
                    <Table.Td miw={360}>
                      <Text fw={600}>{item.question_text}</Text>
                      <Text size="xs" c="dimmed">
                        {item.category} · {item.student_name} ·{" "}
                        {new Date(item.interviewed_at).toLocaleDateString(
                          "ru-RU",
                        )}
                      </Text>
                    </Table.Td>
                    <Table.Td>{item.track_title}</Table.Td>
                    <Table.Td>{item.company_name}</Table.Td>
                    <Table.Td>
                      <Badge
                        color={
                          item.moderation_status === "approved"
                            ? "green"
                            : item.moderation_status === "rejected"
                              ? "gray"
                              : "yellow"
                        }
                      >
                        {statusLabels[item.moderation_status]}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Button
                        component={Link}
                        to={`/admin/interview-question-moderation/${item.question_id}`}
                        size="xs"
                        variant="light"
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
      {pages > 1 && (
        <Pagination value={page} onChange={setPage} total={pages} />
      )}
    </Stack>
  );
}
