import {
  Alert,
  Button,
  Card,
  Group,
  Modal,
  Pagination,
  Stack,
  Text,
  TextInput,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api } from "../../api/endpoints";
import type {
  InterviewCardDuplicateCandidate,
  InterviewCardDuplicateCard,
} from "../../types/api";

export function DuplicateReports({
  onCompare,
}: {
  onCompare: (candidate: InterviewCardDuplicateCandidate) => void;
}) {
  const [page, setPage] = useState(1);
  const [source, setSource] = useState<InterviewCardDuplicateCard | null>(null);
  const [search, setSearch] = useState("");
  const [query] = useDebouncedValue(search.trim(), 300);
  const client = useQueryClient();
  const reports = useQuery({
    queryKey: ["duplicate-reports", page],
    queryFn: () => api.adminDuplicateReports((page - 1) * 20),
  });
  const targets = useQuery({
    queryKey: ["duplicate-report-targets", source?.id, query],
    queryFn: () => api.duplicateReportTargets(source!.id, query),
    enabled: !!source && query.length >= 2,
  });
  const dismiss = useMutation({
    mutationFn: api.dismissDuplicateReports,
    onSuccess: async () => {
      setPage(1);
      await client.invalidateQueries({ queryKey: ["duplicate-reports"] });
    },
    onError: (error: Error) =>
      notifications.show({ color: "red", message: error.message }),
  });
  return (
    <Card withBorder radius="lg" padding="lg">
      <Stack>
        <Text fw={700}>
          Сообщения пользователей о дублях
          {reports.data ? `: ${reports.data.total}` : ""}
        </Text>
        {reports.isError && <Alert color="red">{reports.error.message}</Alert>}
        {reports.isPending && <Text c="dimmed">Загружаем сообщения…</Text>}
        {reports.data?.total === 0 && (
          <Text c="dimmed">Новых сообщений нет.</Text>
        )}
        {reports.data?.items.map(({ card, reports_count }) => (
          <Card key={card.id} withBorder>
            <Stack gap="xs">
              <Text fw={600}>{card.question_markdown}</Text>
              <Text size="sm" c="dimmed">
                {card.direction_title} · Сообщений: {reports_count}
              </Text>
              <Group>
                <Button
                  variant="light"
                  onClick={() => {
                    setSource(card);
                    setSearch("");
                  }}
                >
                  Найти вторую карточку
                </Button>
                <Button
                  variant="subtle"
                  disabled={dismiss.isPending}
                  onClick={() => dismiss.mutate(card.id)}
                >
                  Отклонить сообщение
                </Button>
              </Group>
            </Stack>
          </Card>
        ))}
        {(reports.data?.total ?? 0) > 20 && (
          <Pagination
            total={Math.ceil((reports.data?.total ?? 0) / 20)}
            value={page}
            onChange={setPage}
          />
        )}
        <Modal
          opened={!!source}
          onClose={() => setSource(null)}
          title="Выбрать вторую карточку"
          size="lg"
        >
          <Stack>
            <Text fw={600}>{source?.question_markdown}</Text>
            <TextInput
              label="Поиск по тексту вопроса или ID карточки"
              value={search}
              onChange={(event) => setSearch(event.currentTarget.value)}
            />
            {targets.isFetching && <Text c="dimmed">Ищем…</Text>}
            {targets.isError && (
              <Alert color="red">{targets.error.message}</Alert>
            )}
            {query.length >= 2 && targets.data?.length === 0 && (
              <Text c="dimmed">
                Не найдено. Попробуйте другие слова из вопроса.
              </Text>
            )}
            {targets.data?.map((target) => (
              <Card key={target.id} withBorder>
                <Stack gap="xs">
                  <Text>{target.question_markdown}</Text>
                  <Button
                    variant="light"
                    onClick={() => {
                      if (!source) return;
                      onCompare({
                        pair_key: [source.id, target.id].sort().join(":"),
                        similarity: 0,
                        matched_source: "user_report",
                        matched_text: target.question_markdown,
                        left: source,
                        right: target,
                      });
                      setSource(null);
                      setPage(1);
                    }}
                  >
                    Сравнить ответы и объединить
                  </Button>
                </Stack>
              </Card>
            ))}
          </Stack>
        </Modal>
      </Stack>
    </Card>
  );
}
