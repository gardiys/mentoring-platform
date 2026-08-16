import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Modal,
  Pagination,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  CARD_AUTOMATION_PAGE_SIZE,
  useManagedPersonalReviewItems,
  useUpdateManagedPersonalReviewItem,
  type CardAutomationScope,
} from "../features/cardAutomation/queries";
import { personalReviewStatusLabels } from "../features/cardAutomation/presentation";
import type {
  CardAutomationAnswerContract,
  ManagedPersonalReviewMutation,
  PersonalReviewFilters,
  PersonalReviewItemRead,
  PersonalReviewStatus,
} from "../types/api";

const statuses: PersonalReviewStatus[] = [
  "active",
  "mastered",
  "archived",
  "replaced_by_canonical_card",
];

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

function datetimeLocalValue(value: string) {
  const date = new Date(value);
  const pad = (part: number) => String(part).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(
    date.getDate(),
  )}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function asStatus(value: string | null): PersonalReviewStatus | null {
  const status = value as PersonalReviewStatus | null;
  return status && statuses.includes(status) ? status : null;
}

function parseAnswerContract(
  value: string,
): CardAutomationAnswerContract | null {
  if (!value.trim()) return null;
  const parsed: unknown = JSON.parse(value);
  if (!parsed || typeof parsed !== "object") {
    throw new Error("Контракт должен быть JSON-объектом");
  }
  const contract = parsed as Partial<CardAutomationAnswerContract>;
  const arrayFields: Array<keyof CardAutomationAnswerContract> = [
    "required_points",
    "optional_points",
    "common_mistakes",
    "unsupported_claims",
    "follow_up_questions",
    "version_scope",
    "source_references",
  ];
  if (
    typeof contract.short_answer !== "string" ||
    !contract.short_answer.trim()
  ) {
    throw new Error("В контракте нужен непустой short_answer");
  }
  if (
    !arrayFields.every(
      (field) =>
        Array.isArray(contract[field]) &&
        (contract[field] as unknown[]).every(
          (item) => typeof item === "string",
        ),
    )
  ) {
    throw new Error("Списки контракта должны содержать только строки");
  }
  if (
    !["junior", "middle", "senior", "mixed"].includes(contract.difficulty ?? "")
  ) {
    throw new Error("difficulty должен быть junior, middle, senior или mixed");
  }
  if (
    typeof contract.confidence !== "number" ||
    contract.confidence < 0 ||
    contract.confidence > 1
  ) {
    throw new Error("confidence должен быть числом от 0 до 1");
  }
  return contract as CardAutomationAnswerContract;
}

function CorrectionDialog({
  item,
  scope,
  studentId,
  onClose,
  reload,
}: {
  item: PersonalReviewItemRead | null;
  scope: CardAutomationScope;
  studentId: string;
  onClose: () => void;
  reload: () => Promise<unknown>;
}) {
  const mutation = useUpdateManagedPersonalReviewItem(scope, studentId);
  const [question, setQuestion] = useState(item?.question_text ?? "");
  const [answerSummary, setAnswerSummary] = useState(
    item?.answer_summary ?? "",
  );
  const initialContract = item?.answer_contract
    ? JSON.stringify(item.answer_contract, null, 2)
    : "";
  const [answerContract, setAnswerContract] = useState(initialContract);
  const initialDueAt = item ? datetimeLocalValue(item.due_at) : "";
  const [dueAt, setDueAt] = useState(initialDueAt);
  const [status, setStatus] = useState<PersonalReviewStatus>(
    item?.status ?? "active",
  );
  const [reason, setReason] = useState("");
  const [contractError, setContractError] = useState<string | null>(null);
  const conflict =
    mutation.error instanceof ApiError && mutation.error.status === 409;
  const dueTimestamp = Date.parse(dueAt);
  const changed = Boolean(
    item &&
    (question.trim() !== item.question_text ||
      answerSummary.trim() !== (item.answer_summary ?? "") ||
      answerContract !== initialContract ||
      dueAt !== initialDueAt ||
      status !== item.status),
  );

  const submit = () => {
    if (!item || !changed || !question.trim() || !reason.trim()) return;
    if (!Number.isFinite(dueTimestamp)) {
      setContractError("Укажите корректную дату следующего повторения");
      return;
    }
    let parsedContract: CardAutomationAnswerContract | null = null;
    if (answerContract !== initialContract) {
      try {
        parsedContract = parseAnswerContract(answerContract);
        setContractError(null);
      } catch (error) {
        setContractError(
          error instanceof Error ? error.message : "Некорректный JSON-контракт",
        );
        return;
      }
    }

    const payload: ManagedPersonalReviewMutation = {
      expected_version: item.version,
      reason: reason.trim(),
    };
    if (question.trim() !== item.question_text) {
      payload.question_text = question.trim();
    }
    if (answerSummary.trim() !== (item.answer_summary ?? "")) {
      payload.answer_summary = answerSummary.trim() || null;
    }
    if (answerContract !== initialContract) {
      payload.answer_contract = parsedContract;
    }
    if (dueAt !== initialDueAt) {
      payload.due_at = new Date(dueTimestamp).toISOString();
    }
    if (status !== item.status) payload.status = status;
    if (
      !window.confirm(
        "Сохранить ручную корректировку личного вопроса? Изменение попадёт в аудит.",
      )
    )
      return;

    mutation.mutate(
      { itemId: item.id, payload },
      {
        onSuccess: () => {
          notifications.show({
            color: "green",
            message: "Личный вопрос ученика обновлён",
          });
          onClose();
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  const statusOptions = statuses
    .filter(
      (value) =>
        value !== "replaced_by_canonical_card" ||
        Boolean(item?.canonical_card_id || item?.replaced_by_card_id),
    )
    .map((value) => ({ value, label: personalReviewStatusLabels[value] }));

  return (
    <Modal
      opened={Boolean(item)}
      onClose={onClose}
      title="Изменить личный вопрос"
      size="xl"
    >
      <Stack>
        <Alert color="blue">
          Редактируйте только проверенные данные. Исходная версия и причина
          изменения сохранятся в журнале решений.
        </Alert>
        <Textarea
          label="Вопрос"
          required
          minRows={3}
          value={question}
          onChange={(event) => setQuestion(event.currentTarget.value)}
        />
        <Textarea
          label="Краткий ответ"
          minRows={4}
          value={answerSummary}
          onChange={(event) => setAnswerSummary(event.currentTarget.value)}
        />
        <TextInput
          type="datetime-local"
          label="Следующее повторение"
          required
          value={dueAt}
          onChange={(event) => setDueAt(event.currentTarget.value)}
        />
        <Select
          label="Статус"
          value={status}
          data={statusOptions}
          onChange={(value) =>
            value && setStatus(value as PersonalReviewStatus)
          }
        />
        <details>
          <summary>Контракт ответа (JSON)</summary>
          <Textarea
            aria-label="Контракт ответа (JSON)"
            description="Пустое значение удалит контракт. Все поля проходят строгую серверную проверку."
            minRows={12}
            mt="sm"
            styles={{ input: { fontFamily: "monospace" } }}
            value={answerContract}
            onChange={(event) => {
              setAnswerContract(event.currentTarget.value);
              setContractError(null);
            }}
          />
        </details>
        <Textarea
          label="Причина изменения"
          required
          minRows={3}
          value={reason}
          onChange={(event) => setReason(event.currentTarget.value)}
        />
        {contractError && <Alert color="red">{contractError}</Alert>}
        {mutation.error && (
          <Alert
            color={conflict ? "yellow" : "red"}
            title={conflict ? "Вопрос уже изменился" : undefined}
          >
            <Stack align="flex-start" gap="sm">
              <Text>{mutation.error.message}</Text>
              {conflict && (
                <Button
                  variant="light"
                  onClick={() => {
                    if (
                      !window.confirm(
                        "Закрыть форму и загрузить актуальную версию вопроса?",
                      )
                    )
                      return;
                    mutation.reset();
                    onClose();
                    void reload();
                  }}
                >
                  Обновить вопрос
                </Button>
              )}
            </Stack>
          </Alert>
        )}
        <Group justify="flex-end">
          <Button
            variant="default"
            onClick={onClose}
            disabled={mutation.isPending}
          >
            Отмена
          </Button>
          <Button
            onClick={submit}
            loading={mutation.isPending}
            disabled={!changed || !question.trim() || !reason.trim()}
          >
            Сохранить корректировку
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export function ManagedPersonalReviewPage({
  scope,
}: {
  scope: CardAutomationScope;
}) {
  const { studentId = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const status = asStatus(searchParams.get("status"));
  const dueBefore = searchParams.get("due_before");
  const filters: PersonalReviewFilters = {
    directionId: null,
    statuses: status ? [status] : [],
    dueOnly: searchParams.get("due_only") === "true",
    dueBefore: dueBefore ? `${dueBefore}T23:59:59.999Z` : null,
    sortOrder: searchParams.get("sort_order") === "desc" ? "desc" : "asc",
  };
  const query = useManagedPersonalReviewItems(scope, studentId, filters, page);
  const [editedItem, setEditedItem] = useState<PersonalReviewItemRead | null>(
    null,
  );

  const updateFilter = (name: string, value: string | null) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(name, value);
        else next.delete(name);
        if (name !== "page") next.delete("page");
        return next;
      },
      { replace: true },
    );
  };

  if (query.isPending)
    return <LoadingState label="Загружаем личные вопросы ученика…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  const pageCount = Math.max(
    1,
    Math.ceil(query.data.total / CARD_AUTOMATION_PAGE_SIZE),
  );

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-start">
        <PageHeader
          eyebrow={
            scope === "admin"
              ? "Администрирование · личная подготовка"
              : "Менторство · личная подготовка"
          }
          title="Личные вопросы ученика"
          description="Проверяйте персональные вопросы, сроки повторения и ответы. Каждая ручная корректировка версионируется и попадает в аудит."
        />
        <Button
          component={Link}
          to={`/mentor/students/${studentId}`}
          variant="light"
        >
          К ученику
        </Button>
      </Group>

      <Card withBorder>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
          <Select
            label="Статус"
            placeholder="Все статусы"
            clearable
            value={status}
            data={statuses.map((value) => ({
              value,
              label: personalReviewStatusLabels[value],
            }))}
            onChange={(value) => updateFilter("status", value)}
          />
          <TextInput
            type="date"
            label="Запланировано до"
            value={dueBefore ?? ""}
            onChange={(event) =>
              updateFilter("due_before", event.currentTarget.value)
            }
          />
          <Select
            label="Сортировка по сроку"
            value={filters.sortOrder}
            data={[
              { value: "asc", label: "Сначала ближайшие" },
              { value: "desc", label: "Сначала поздние" },
            ]}
            onChange={(value) => updateFilter("sort_order", value)}
          />
          <Stack justify="flex-end" gap="xs">
            <Switch
              label="Только требующие повторения"
              checked={filters.dueOnly}
              onChange={(event) =>
                updateFilter(
                  "due_only",
                  event.currentTarget.checked ? "true" : null,
                )
              }
            />
            <Button
              variant="subtle"
              w="fit-content"
              onClick={() => setSearchParams({}, { replace: true })}
              disabled={searchParams.size === 0}
            >
              Сбросить фильтры
            </Button>
          </Stack>
        </SimpleGrid>
      </Card>

      <Text fw={600}>Личных вопросов: {query.data.total}</Text>

      {query.data.items.length === 0 ? (
        <Card withBorder>
          <Title order={3}>По этим фильтрам вопросов нет</Title>
          <Text size="sm" c="dimmed" mt={4}>
            Сбросьте фильтры или проверьте, включено ли персональное повторение
            для направления ученика.
          </Text>
        </Card>
      ) : (
        <Stack>
          {query.data.items.map((item) => (
            <Card key={item.id} withBorder>
              <Stack>
                <Group justify="space-between" align="flex-start">
                  <div>
                    <Group gap="xs" mb="xs">
                      <Badge>{item.direction_title}</Badge>
                      <Badge variant="outline">
                        {personalReviewStatusLabels[item.status]}
                      </Badge>
                    </Group>
                    <Title order={3}>{item.question_text}</Title>
                  </div>
                  <Button variant="light" onClick={() => setEditedItem(item)}>
                    Редактировать
                  </Button>
                </Group>
                <div className="markdown-content">
                  <ReactMarkdown>
                    {item.answer_contract?.short_answer ??
                      item.answer_summary ??
                      "Проверенного ответа пока нет."}
                  </ReactMarkdown>
                </div>
                <Group gap="xl">
                  <Text size="sm" c="dimmed">
                    Следующее повторение: {formatDate(item.due_at)}
                  </Text>
                  <Text size="sm" c="dimmed">
                    Успешных повторов: {item.successful_reviews_count}
                  </Text>
                  <Text size="sm" c="dimmed">
                    Версия: {item.version}
                  </Text>
                </Group>
              </Stack>
            </Card>
          ))}
        </Stack>
      )}

      {pageCount > 1 && (
        <Pagination
          value={page}
          total={pageCount}
          disabled={query.isPlaceholderData}
          onChange={(value) => updateFilter("page", String(value))}
          mx="auto"
        />
      )}

      <CorrectionDialog
        key={editedItem ? `${editedItem.id}:${editedItem.version}` : "closed"}
        item={editedItem}
        scope={scope}
        studentId={studentId}
        onClose={() => setEditedItem(null)}
        reload={() => query.refetch()}
      />
    </Stack>
  );
}

export function MentorManagedPersonalReviewPage() {
  return <ManagedPersonalReviewPage scope="mentor" />;
}

export function AdminManagedPersonalReviewPage() {
  return <ManagedPersonalReviewPage scope="admin" />;
}
