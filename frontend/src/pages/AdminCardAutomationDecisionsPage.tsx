import {
  Alert,
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  Modal,
  Pagination,
  Select,
  SimpleGrid,
  Stack,
  Table,
  Text,
  TextInput,
  Textarea,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useAdminTracks } from "../features/admin/queries";
import { CardAutomationNavigation } from "../features/cardAutomation/CardAutomationNavigation";
import {
  CARD_AUTOMATION_PAGE_SIZE,
  useAutomationDecisions,
  useOverrideAutomationDecision,
  useReviewAutomationDecision,
  type CardAutomationScope,
} from "../features/cardAutomation/queries";
import {
  decisionSourceLabels,
  decisionTypeColors,
  decisionTypeLabels,
  percent,
  reviewResultLabels,
} from "../features/cardAutomation/presentation";
import type {
  AutomationDecisionFilters,
  AutomationDecisionRead,
  AutomationDecisionSource,
  AutomationDecisionType,
  AutomationReviewResult,
} from "../types/api";

const decisionTypes: AutomationDecisionType[] = [
  "question_routed",
  "routed_as_noise",
  "routed_as_non_flashcard",
  "exact_card_match",
  "alias_card_match",
  "semantic_card_match",
  "cluster_match",
  "shadow_cluster_created",
  "cluster_promoted",
  "personal_review_created",
  "personal_review_reviewed",
  "personal_review_archived",
  "answer_contract_generated",
  "answer_contract_validated",
  "answer_contract_needs_source",
  "answer_contract_failed",
  "answer_validation_failed",
  "manual_override",
  "cluster_linked",
  "card_created",
  "cluster_split",
  "cluster_merged",
  "cluster_ignored",
  "cluster_deferred",
  "cluster_reopened",
  "cluster_marked_important",
  "occurrence_failed",
  "occurrence_reprocessed",
];

const decisionSources: AutomationDecisionSource[] = [
  "rule",
  "ai_routing",
  "exact",
  "confirmed_alias",
  "semantic_judge",
  "clustering",
  "human",
  "backfill",
];

const reviewResults: AutomationReviewResult[] = [
  "correct",
  "merge_error",
  "classification_error",
  "wrong_object_type",
  "wrong_topic",
  "other",
];

function asDecisionType(value: string | null) {
  const type = value as AutomationDecisionType | null;
  return type && decisionTypes.includes(type) ? type : null;
}

function asDecisionSource(value: string | null) {
  const source = value as AutomationDecisionSource | null;
  return source && decisionSources.includes(source) ? source : null;
}

function filtersFromParams(params: URLSearchParams): AutomationDecisionFilters {
  const decisionType = asDecisionType(params.get("decision_type"));
  const decisionSource = asDecisionSource(params.get("decision_source"));
  const review = params.get("review");
  const overridden = params.get("overridden");
  const createdFrom = params.get("created_from");
  const createdTo = params.get("created_to");
  return {
    directionId: params.get("direction_id"),
    entityType: params.get("entity_type"),
    decisionTypes: decisionType ? [decisionType] : [],
    decisionSources: decisionSource ? [decisionSource] : [],
    isAuditSample: params.get("audit_sample") === "true" ? true : null,
    isReviewed:
      review === "reviewed" ? true : review === "pending" ? false : null,
    isOverridden:
      overridden === "yes" ? true : overridden === "no" ? false : null,
    createdFrom: createdFrom ? `${createdFrom}T00:00:00.000Z` : null,
    createdTo: createdTo ? `${createdTo}T23:59:59.999Z` : null,
    sortOrder: params.get("sort_order") === "asc" ? "asc" : "desc",
  };
}

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString("ru-RU") : "—";
}

function targetLabel(decision: AutomationDecisionRead) {
  return (
    decision.selected_card_question ??
    decision.selected_cluster_question ??
    decision.selected_card_id ??
    decision.selected_cluster_id ??
    "—"
  );
}

interface ReviewDialogProps {
  decision: AutomationDecisionRead | null;
  onClose: () => void;
  reload: () => Promise<unknown>;
  scope: CardAutomationScope;
}

function ReviewDialog({ decision, onClose, reload, scope }: ReviewDialogProps) {
  const mutation = useReviewAutomationDecision(scope);
  const [result, setResult] = useState<AutomationReviewResult>("correct");
  const [reason, setReason] = useState("");
  const reasonRequired = result === "other";
  const conflict =
    mutation.error instanceof ApiError && mutation.error.status === 409;

  const submit = () => {
    if (!decision || (reasonRequired && !reason.trim())) return;
    mutation.mutate(
      {
        decisionId: decision.id,
        payload: { result, reason: reason.trim() || null },
      },
      {
        onSuccess: () => {
          notifications.show({ color: "green", message: "Проверка сохранена" });
          onClose();
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Modal
      opened={Boolean(decision)}
      onClose={onClose}
      title="Проверить решение"
    >
      <Stack>
        <Text size="sm" fw={600}>
          {decision ? decisionTypeLabels[decision.decision_type] : ""}
        </Text>
        <Select
          label="Результат проверки"
          value={result}
          data={reviewResults.map((value) => ({
            value,
            label: reviewResultLabels[value],
          }))}
          onChange={(value) =>
            setResult((value as AutomationReviewResult | null) ?? "correct")
          }
        />
        <Textarea
          label={reasonRequired ? "Комментарий (обязательно)" : "Комментарий"}
          minRows={4}
          value={reason}
          onChange={(event) => setReason(event.currentTarget.value)}
        />
        {mutation.error && (
          <Alert color={conflict ? "yellow" : "red"}>
            <Stack align="flex-start" gap="sm">
              <Text>{mutation.error.message}</Text>
              {conflict && (
                <Button
                  variant="light"
                  onClick={() => {
                    if (!window.confirm("Закрыть форму и обновить журнал?"))
                      return;
                    mutation.reset();
                    onClose();
                    void reload();
                  }}
                >
                  Обновить журнал
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
            disabled={reasonRequired && !reason.trim()}
          >
            Сохранить проверку
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

interface OverrideDialogProps {
  decision: AutomationDecisionRead | null;
  onClose: () => void;
  reload: () => Promise<unknown>;
  scope: CardAutomationScope;
}

function OverrideDialog({
  decision,
  onClose,
  reload,
  scope,
}: OverrideDialogProps) {
  const mutation = useOverrideAutomationDecision(scope);
  const [replacementType, setReplacementType] =
    useState<AutomationDecisionType>("manual_override");
  const [cardId, setCardId] = useState("");
  const [clusterId, setClusterId] = useState("");
  const [reason, setReason] = useState("");
  const hasBothTargets = Boolean(cardId.trim() && clusterId.trim());
  const conflict =
    mutation.error instanceof ApiError && mutation.error.status === 409;

  const submit = () => {
    if (!decision || !reason.trim() || hasBothTargets) return;
    if (decision.entity_version == null) return;
    if (
      !window.confirm(
        "Отменить исходное автоматическое решение и записать замену в аудит?",
      )
    )
      return;
    mutation.mutate(
      {
        decisionId: decision.id,
        payload: {
          expected_entity_version: decision.entity_version,
          replacement_decision_type: replacementType,
          selected_card_id: cardId.trim() || null,
          selected_cluster_id: clusterId.trim() || null,
          reason: reason.trim(),
        },
      },
      {
        onSuccess: () => {
          notifications.show({
            color: "green",
            message: "Автоматическое решение отменено",
          });
          onClose();
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Modal
      opened={Boolean(decision)}
      onClose={onClose}
      title="Отменить автоматическое решение"
      size="lg"
    >
      <Stack>
        <Alert color="yellow">
          Это действие не удаляет историю: исходное решение останется в журнале
          с отметкой об отмене.
        </Alert>
        <Select
          searchable
          label="Новое решение"
          value={replacementType}
          data={decisionTypes.map((value) => ({
            value,
            label: decisionTypeLabels[value],
          }))}
          onChange={(value) =>
            setReplacementType(
              (value as AutomationDecisionType | null) ?? "manual_override",
            )
          }
        />
        <TextInput
          label="ID выбранной карточки"
          description="Заполняйте либо карточку, либо кластер"
          value={cardId}
          onChange={(event) => setCardId(event.currentTarget.value)}
        />
        <TextInput
          label="ID выбранного кластера"
          value={clusterId}
          onChange={(event) => setClusterId(event.currentTarget.value)}
        />
        {hasBothTargets && (
          <Alert color="red">
            Нельзя одновременно выбрать карточку и кластер.
          </Alert>
        )}
        <Textarea
          label="Причина отмены"
          minRows={4}
          required
          value={reason}
          onChange={(event) => setReason(event.currentTarget.value)}
        />
        {mutation.error && (
          <Alert color={conflict ? "yellow" : "red"}>
            <Stack align="flex-start" gap="sm">
              <Text>{mutation.error.message}</Text>
              {conflict && (
                <Button
                  variant="light"
                  onClick={() => {
                    if (!window.confirm("Закрыть форму и обновить журнал?"))
                      return;
                    mutation.reset();
                    onClose();
                    void reload();
                  }}
                >
                  Обновить журнал
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
            color="orange"
            onClick={submit}
            loading={mutation.isPending}
            disabled={!reason.trim() || hasBothTargets}
          >
            Отменить и заменить
          </Button>
        </Group>
      </Stack>
    </Modal>
  );
}

export function CardAutomationDecisionsPage({
  scope,
}: {
  scope: CardAutomationScope;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const parsedFilters = filtersFromParams(searchParams);
  const filters = {
    ...parsedFilters,
    directionId: scope === "admin" ? parsedFilters.directionId : null,
  };
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const query = useAutomationDecisions(filters, page, scope);
  const tracks = useAdminTracks(scope === "admin");
  const [reviewedDecision, setReviewedDecision] =
    useState<AutomationDecisionRead | null>(null);
  const [overriddenDecision, setOverriddenDecision] =
    useState<AutomationDecisionRead | null>(null);

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
    return <LoadingState label="Загружаем журнал решений…" />;
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
      <PageHeader
        eyebrow={
          scope === "admin"
            ? "Администрирование · безопасная автоматизация"
            : "Менторство · аудит своих направлений"
        }
        title="Технический журнал автоматизации"
        description="Служебная история работы моделей и правил. Она нужна для диагностики и аудита, но не для обычной проверки содержания карточек."
      />
      <CardAutomationNavigation scope={scope} />

      <Alert color="blue" title="Хотите проверить тему, вопрос и ответ?">
        <Group justify="space-between" align="center">
          <Text size="sm">
            Перейдите в очередь карточек: там показан итог AI, его можно
            отредактировать, связать с существующей карточкой или опубликовать
            как новую.
          </Text>
          <Button
            component={Link}
            to={`/${scope}/card-automation/clusters`}
            variant="light"
          >
            К карточкам на проверку
          </Button>
        </Group>
      </Alert>

      <Card withBorder>
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
          {scope === "admin" && (
            <Select
              label="Направление"
              placeholder="Все направления"
              clearable
              searchable
              value={filters.directionId}
              data={(tracks.data ?? []).map((track) => ({
                value: track.id,
                label: track.title,
              }))}
              onChange={(value) => updateFilter("direction_id", value)}
            />
          )}
          <Select
            label="Тип решения"
            placeholder="Все типы"
            clearable
            searchable
            value={filters.decisionTypes[0] ?? null}
            data={decisionTypes.map((value) => ({
              value,
              label: decisionTypeLabels[value],
            }))}
            onChange={(value) => updateFilter("decision_type", value)}
          />
          <Select
            label="Источник"
            placeholder="Все источники"
            clearable
            value={filters.decisionSources[0] ?? null}
            data={decisionSources.map((value) => ({
              value,
              label: decisionSourceLabels[value],
            }))}
            onChange={(value) => updateFilter("decision_source", value)}
          />
          <TextInput
            label="Тип сущности"
            placeholder="question_cluster"
            value={filters.entityType ?? ""}
            onChange={(event) =>
              updateFilter("entity_type", event.currentTarget.value)
            }
          />
          <Select
            label="Проверка"
            value={searchParams.get("review") ?? "all"}
            data={[
              { value: "all", label: "Все" },
              { value: "pending", label: "Не проверены" },
              { value: "reviewed", label: "Проверены" },
            ]}
            onChange={(value) =>
              updateFilter("review", value === "all" ? null : value)
            }
          />
          <Select
            label="Отмена"
            value={searchParams.get("overridden") ?? "all"}
            data={[
              { value: "all", label: "Все" },
              { value: "yes", label: "Отменённые" },
              { value: "no", label: "Не отменённые" },
            ]}
            onChange={(value) =>
              updateFilter("overridden", value === "all" ? null : value)
            }
          />
          <TextInput
            type="date"
            label="Создано с"
            value={searchParams.get("created_from") ?? ""}
            onChange={(event) =>
              updateFilter("created_from", event.currentTarget.value)
            }
          />
          <TextInput
            type="date"
            label="Создано до"
            value={searchParams.get("created_to") ?? ""}
            onChange={(event) =>
              updateFilter("created_to", event.currentTarget.value)
            }
          />
          <Stack justify="flex-end" gap="xs">
            <Checkbox
              label="Только выборка аудита"
              checked={filters.isAuditSample === true}
              onChange={(event) =>
                updateFilter(
                  "audit_sample",
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

      <Group justify="space-between">
        <Text fw={600}>Решений: {query.data.total}</Text>
        {query.isFetching && (
          <Text size="xs" c="dimmed" role="status">
            Обновляем журнал…
          </Text>
        )}
      </Group>

      {query.data.items.length === 0 ? (
        <Card withBorder>
          <Text fw={600}>Решений по этим фильтрам нет</Text>
          <Text size="sm" c="dimmed" mt={4}>
            Сбросьте фильтры или дождитесь следующего запуска pipeline.
          </Text>
        </Card>
      ) : (
        <Card withBorder p={0}>
          <Table.ScrollContainer minWidth={1560}>
            <Table verticalSpacing="sm" horizontalSpacing="md" stickyHeader>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Решение</Table.Th>
                  <Table.Th>Вопрос</Table.Th>
                  <Table.Th>Выбранный объект</Table.Th>
                  <Table.Th>Confidence / similarity</Table.Th>
                  <Table.Th>Модель</Table.Th>
                  <Table.Th>Дата</Table.Th>
                  <Table.Th>Аудит</Table.Th>
                  <Table.Th>Статус</Table.Th>
                  <Table.Th aria-label="Действия" />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {query.data.items.map((decision) => (
                  <Table.Tr key={decision.id}>
                    <Table.Td miw={210}>
                      <Badge
                        color={decisionTypeColors[decision.decision_type]}
                        variant="light"
                      >
                        {decisionTypeLabels[decision.decision_type]}
                      </Badge>
                      <Text size="xs" c="dimmed">
                        {decisionSourceLabels[decision.decision_source]}
                      </Text>
                    </Table.Td>
                    <Table.Td miw={300}>
                      <Text lineClamp={3}>
                        {decision.question_text ?? "Без текста вопроса"}
                      </Text>
                      <Text size="xs" c="dimmed">
                        {decision.entity_type} · {decision.entity_id}
                      </Text>
                    </Table.Td>
                    <Table.Td miw={260}>
                      <Text lineClamp={3}>{targetLabel(decision)}</Text>
                    </Table.Td>
                    <Table.Td>
                      <Text>{percent(decision.confidence)}</Text>
                      <Text size="xs" c="dimmed">
                        similarity {percent(decision.similarity_score)}
                      </Text>
                    </Table.Td>
                    <Table.Td miw={180}>
                      <Text size="sm">
                        {[decision.model_provider, decision.model_name]
                          .filter(Boolean)
                          .join(" / ") || "Правило без модели"}
                      </Text>
                      <Text size="xs" c="dimmed">
                        prompt {decision.prompt_version ?? "—"}
                      </Text>
                    </Table.Td>
                    <Table.Td>{formatDate(decision.created_at)}</Table.Td>
                    <Table.Td>
                      {decision.is_audit_sample && (
                        <Badge variant="light">В выборке</Badge>
                      )}
                      <Text size="xs" mt={4}>
                        {decision.review_result
                          ? reviewResultLabels[decision.review_result]
                          : "Не проверено"}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      {decision.is_overridden ? (
                        <Badge color="orange">Отменено</Badge>
                      ) : (
                        <Badge color="green" variant="light">
                          Действует
                        </Badge>
                      )}
                      {decision.override_reason && (
                        <Text size="xs" c="dimmed" mt={4} lineClamp={2}>
                          {decision.override_reason}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      <Stack gap="xs">
                        <Button
                          size="xs"
                          variant="light"
                          onClick={() => setReviewedDecision(decision)}
                        >
                          Проверить техрешение
                        </Button>
                        {!decision.is_overridden && (
                          <Button
                            size="xs"
                            variant="subtle"
                            color="orange"
                            onClick={() => setOverriddenDecision(decision)}
                            disabled={decision.entity_version == null}
                          >
                            Отменить
                          </Button>
                        )}
                        {decision.selected_cluster_id && (
                          <Button
                            component={Link}
                            to={`/${scope}/card-automation/clusters/${decision.selected_cluster_id}`}
                            size="xs"
                            variant="transparent"
                          >
                            Открыть карточку
                          </Button>
                        )}
                      </Stack>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
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

      <ReviewDialog
        key={`review:${reviewedDecision?.id ?? "closed"}`}
        decision={reviewedDecision}
        onClose={() => setReviewedDecision(null)}
        reload={() => query.refetch()}
        scope={scope}
      />
      <OverrideDialog
        key={`override:${overriddenDecision?.id ?? "closed"}`}
        decision={overriddenDecision}
        onClose={() => setOverriddenDecision(null)}
        reload={() => query.refetch()}
        scope={scope}
      />
    </Stack>
  );
}

export function AdminCardAutomationDecisionsPage() {
  return <CardAutomationDecisionsPage scope="admin" />;
}
