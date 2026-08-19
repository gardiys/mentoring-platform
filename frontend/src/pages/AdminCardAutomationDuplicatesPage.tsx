import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  Modal,
  Pagination,
  Radio,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  Textarea,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { useSearchParams } from "react-router-dom";

import { api } from "../api/endpoints";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useAdminTracks } from "../features/admin/queries";
import { CardAutomationNavigation } from "../features/cardAutomation/CardAutomationNavigation";
import type {
  InterviewCardDuplicateCandidate,
  InterviewCardDuplicateCard,
} from "../types/api";

const PAGE_SIZE = 20;

function idempotencyKey() {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(36).slice(2)}`
  );
}

function percentage(value: number) {
  return `${Math.round(value * 100)}%`;
}

function CardComparison({
  card,
  selected,
  onSelect,
}: {
  card: InterviewCardDuplicateCard;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <Card
      withBorder
      radius="lg"
      padding="lg"
      onClick={onSelect}
      style={{
        cursor: "pointer",
        borderColor: selected
          ? "var(--mantine-color-blue-5)"
          : "var(--mantine-color-default-border)",
      }}
    >
      <Stack gap="md">
        <Radio
          checked={selected}
          onChange={onSelect}
          label={selected ? "Основная карточка" : "Сделать основной"}
          value={card.id}
        />
        <Group gap="xs">
          <Badge variant="light">{card.direction_title}</Badge>
          <Badge variant="outline">{card.category}</Badge>
          {card.subcategory && (
            <Badge variant="outline">{card.subcategory}</Badge>
          )}
          <Badge color="gray" variant="light">
            Спрошено: {card.asked_count}
          </Badge>
        </Group>
        <Stack gap={4}>
          <Text size="xs" c="dimmed" fw={700} tt="uppercase">
            Вопрос
          </Text>
          <div className="markdown-content">
            <ReactMarkdown>{card.question_markdown}</ReactMarkdown>
          </div>
        </Stack>
        <Stack gap={4}>
          <Text size="xs" c="dimmed" fw={700} tt="uppercase">
            Ответ
          </Text>
          <div className="markdown-content">
            <ReactMarkdown>{card.answer_markdown}</ReactMarkdown>
          </div>
        </Stack>
        {card.companies && (
          <Text size="sm" c="dimmed">
            Компании: {card.companies}
          </Text>
        )}
      </Stack>
    </Card>
  );
}

export function AdminCardAutomationDuplicatesPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const directionId = searchParams.get("direction_id");
  const thresholdValue = Number(searchParams.get("minimum_similarity"));
  const minimumSimilarity = [0.35, 0.5, 0.65, 0.75].includes(thresholdValue)
    ? thresholdValue
    : 0.35;
  const [candidate, setCandidate] =
    useState<InterviewCardDuplicateCandidate | null>(null);
  const [primaryCardId, setPrimaryCardId] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const queryClient = useQueryClient();
  const tracks = useAdminTracks();
  const queryKey = [
    "card-automation",
    "admin",
    "duplicates",
    directionId,
    minimumSimilarity,
    page,
  ] as const;
  const duplicates = useQuery({
    queryKey,
    queryFn: () =>
      api.adminInterviewCardDuplicates({
        directionId,
        minimumSimilarity,
        limit: PAGE_SIZE,
        offset: (page - 1) * PAGE_SIZE,
      }),
  });

  const closeComparison = () => {
    setCandidate(null);
    setPrimaryCardId(null);
    setReason("");
    setConfirmed(false);
  };
  const openComparison = (item: InterviewCardDuplicateCandidate) => {
    setCandidate(item);
    setPrimaryCardId(
      item.left.asked_count >= item.right.asked_count
        ? item.left.id
        : item.right.id,
    );
    setReason("");
    setConfirmed(false);
  };

  const mutation = useMutation({
    mutationFn: async (action: "merge" | "dismiss") => {
      if (!candidate) throw new Error("Пара карточек не выбрана");
      const common = {
        left_card_id: candidate.left.id,
        right_card_id: candidate.right.id,
        expected_left_updated_at: candidate.left.updated_at,
        expected_right_updated_at: candidate.right.updated_at,
        reason: reason.trim(),
      };
      if (action === "dismiss") {
        return api.dismissAdminInterviewCardDuplicate(common, idempotencyKey());
      }
      if (!primaryCardId) throw new Error("Выберите основную карточку");
      return api.mergeAdminInterviewCardDuplicate(
        { ...common, primary_card_id: primaryCardId },
        idempotencyKey(),
      );
    },
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({
        queryKey: ["card-automation", "admin", "duplicates"],
      });
      notifications.show({
        color: "green",
        message:
          result.decision === "merged"
            ? `Карточки объединены. Перенесено появлений: ${result.moved_occurrences}, прогрессов: ${result.merged_progress_records}.`
            : "Пара помечена как разные карточки и больше не появится в очереди.",
      });
      closeComparison();
    },
    onError: (error: Error) =>
      notifications.show({ color: "red", message: error.message }),
  });

  const updateFilter = (name: string, value: string | null) => {
    setSearchParams((current) => {
      const next = new URLSearchParams(current);
      if (value) next.set(name, value);
      else next.delete(name);
      next.delete("page");
      return next;
    });
  };

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow="Собеседования · качество базы"
        title="Дубли карточек"
        description="Сравните похожие вопросы и явно выберите основную карточку. Система перенесёт статистику и прогресс, а вторую карточку оставит в архиве."
      />
      <CardAutomationNavigation />

      <Card withBorder radius="lg" padding="lg">
        <SimpleGrid cols={{ base: 1, sm: 2 }}>
          <Select
            label="Направление"
            placeholder="Все направления"
            clearable
            searchable
            value={directionId}
            data={(tracks.data ?? []).map((track) => ({
              value: track.id,
              label: track.title,
            }))}
            onChange={(value) => updateFilter("direction_id", value)}
          />
          <Select
            label="Минимальное сходство"
            value={String(minimumSimilarity)}
            data={[
              { value: "0.35", label: "35% — широкий поиск" },
              { value: "0.5", label: "50% — похожие" },
              { value: "0.65", label: "65% — вероятные дубли" },
              { value: "0.75", label: "75% — почти точные" },
            ]}
            onChange={(value) =>
              updateFilter("minimum_similarity", value ?? "0.35")
            }
          />
        </SimpleGrid>
      </Card>

      {duplicates.isLoading && <LoadingState />}
      {duplicates.isError && (
        <ErrorState
          error={duplicates.error}
          retry={() => void duplicates.refetch()}
        />
      )}
      {duplicates.data && duplicates.data.items.length === 0 && (
        <Alert color="brandBlue" title="Непроверенных дублей не найдено">
          Попробуйте снизить порог сходства или выбрать другое направление.
        </Alert>
      )}
      {duplicates.data && duplicates.data.items.length > 0 && (
        <Card withBorder radius="lg" padding={0}>
          <Table.ScrollContainer minWidth={980}>
            <Table verticalSpacing="md" horizontalSpacing="lg" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Сходство</Table.Th>
                  <Table.Th>Первая карточка</Table.Th>
                  <Table.Th>Вторая карточка</Table.Th>
                  <Table.Th>Статистика</Table.Th>
                  <Table.Th />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {duplicates.data.items.map((item) => (
                  <Table.Tr
                    key={item.pair_key}
                    tabIndex={0}
                    onClick={() => openComparison(item)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter" || event.key === " ") {
                        event.preventDefault();
                        openComparison(item);
                      }
                    }}
                    style={{ cursor: "pointer" }}
                  >
                    <Table.Td>
                      <Badge color={item.similarity >= 0.72 ? "green" : "blue"}>
                        {percentage(item.similarity)}
                      </Badge>
                    </Table.Td>
                    <Table.Td maw={340}>
                      <Text fw={700} lineClamp={3}>
                        {item.left.question_markdown}
                      </Text>
                      <Text size="xs" c="dimmed" mt={4}>
                        {item.left.category}
                      </Text>
                    </Table.Td>
                    <Table.Td maw={340}>
                      <Text fw={700} lineClamp={3}>
                        {item.right.question_markdown}
                      </Text>
                      <Text size="xs" c="dimmed" mt={4}>
                        {item.right.category}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Text size="sm">
                        {item.left.asked_count} + {item.right.asked_count}{" "}
                        появлений
                      </Text>
                      <Text size="xs" c="dimmed">
                        {item.left.direction_title}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Button
                        variant="light"
                        onClick={(event) => {
                          event.stopPropagation();
                          openComparison(item);
                        }}
                      >
                        Сравнить
                      </Button>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}

      {(duplicates.data?.total ?? 0) > PAGE_SIZE && (
        <Pagination
          value={page}
          total={Math.ceil((duplicates.data?.total ?? 0) / PAGE_SIZE)}
          onChange={(value) =>
            setSearchParams((current) => {
              const next = new URLSearchParams(current);
              next.set("page", String(value));
              return next;
            })
          }
        />
      )}

      <Modal
        opened={candidate !== null}
        onClose={closeComparison}
        title="Проверка похожих карточек"
        size="90rem"
        centered
      >
        {candidate && (
          <Stack gap="lg">
            <Alert
              color="brandBlue"
              title={`Сходство ${percentage(candidate.similarity)}`}
            >
              Проверьте, требуют ли вопросы одного и того же ответа и проверяют
              ли одинаковый объём знаний. Основная карточка сохранит свой вопрос
              и ответ.
            </Alert>
            <SimpleGrid cols={{ base: 1, md: 2 }}>
              <CardComparison
                card={candidate.left}
                selected={primaryCardId === candidate.left.id}
                onSelect={() => setPrimaryCardId(candidate.left.id)}
              />
              <CardComparison
                card={candidate.right}
                selected={primaryCardId === candidate.right.id}
                onSelect={() => setPrimaryCardId(candidate.right.id)}
              />
            </SimpleGrid>
            <Textarea
              label="Причина решения"
              description="Она останется в журнале и поможет восстановить контекст решения."
              minRows={3}
              value={reason}
              onChange={(event) => setReason(event.currentTarget.value)}
              placeholder="Например: вопросы проверяют одинаковое понимание индексов"
              required
            />
            <Checkbox
              checked={confirmed}
              onChange={(event) => setConfirmed(event.currentTarget.checked)}
              label="Я проверил оба ответа и подтверждаю объединение"
            />
            {mutation.isError && (
              <Alert color="red" title="Не удалось сохранить решение">
                {mutation.error.message}
              </Alert>
            )}
            <Group justify="space-between" align="flex-end">
              <Button
                variant="light"
                color="gray"
                disabled={reason.trim().length < 3 || mutation.isPending}
                loading={mutation.isPending}
                onClick={() => mutation.mutate("dismiss")}
              >
                Это разные карточки
              </Button>
              <Stack gap={4} align="flex-end">
                <Title order={5}>Основная карточка будет сохранена</Title>
                <Button
                  color="brandYellow"
                  disabled={
                    !primaryCardId ||
                    !confirmed ||
                    reason.trim().length < 3 ||
                    mutation.isPending
                  }
                  loading={mutation.isPending}
                  onClick={() => mutation.mutate("merge")}
                >
                  Объединить карточки
                </Button>
              </Stack>
            </Group>
          </Stack>
        )}
      </Modal>
    </Stack>
  );
}
