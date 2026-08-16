import {
  Badge,
  Button,
  Card,
  Checkbox,
  Group,
  NumberInput,
  Pagination,
  Select,
  SimpleGrid,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
} from "@mantine/core";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useAdminTracks } from "../features/admin/queries";
import { CardAutomationNavigation } from "../features/cardAutomation/CardAutomationNavigation";
import { ClusterBulkActions } from "../features/cardAutomation/ClusterBulkActions";
import {
  CARD_AUTOMATION_PAGE_SIZE,
  useQuestionClusters,
  type CardAutomationScope,
} from "../features/cardAutomation/queries";
import {
  clusterStatusColors,
  clusterStatusLabels,
  decisionSourceLabels,
  judgeDecisionLabels,
  learningObjectLabels,
  percent,
} from "../features/cardAutomation/presentation";
import type {
  AutomationDecisionSource,
  LearningObjectType,
  QuestionClusterFilters,
  QuestionClusterStatus,
  QuestionClusterSummary,
} from "../types/api";

const clusterStatuses: QuestionClusterStatus[] = [
  "shadow",
  "candidate",
  "needs_review",
  "linked",
  "card_created",
  "deferred",
  "ignored",
  "split",
  "merged",
];

const learningObjectTypes: LearningObjectType[] = [
  "flashcard",
  "open_technical_question",
  "coding_task",
  "system_design_case",
  "behavioral_question",
  "organizational_question",
  "context_dependent",
  "noise",
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

const emptyClusters: QuestionClusterSummary[] = [];

const sortOptions: Array<{
  value: QuestionClusterFilters["sortBy"];
  label: string;
}> = [
  { value: "priority_score", label: "Приоритет" },
  { value: "last_seen_at", label: "Последнее появление" },
  { value: "first_seen_at", label: "Первое появление" },
  { value: "occurrences_count", label: "Количество появлений" },
  { value: "cluster_confidence", label: "Confidence" },
];

function nullablePositiveInt(value: string | null) {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : null;
}

function nullableConfidence(value: string | null) {
  if (!value) return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 && parsed <= 1 ? parsed : null;
}

function filtersFromParams(params: URLSearchParams): QuestionClusterFilters {
  const status = params.get("status") as QuestionClusterStatus | null;
  const objectType = params.get(
    "learning_object_type",
  ) as LearningObjectType | null;
  const decisionSource = params.get(
    "decision_source",
  ) as AutomationDecisionSource | null;
  const sortBy = params.get("sort_by") as
    QuestionClusterFilters["sortBy"] | null;
  const seenFrom = params.get("seen_from");
  const seenTo = params.get("seen_to");

  return {
    directionId: params.get("direction_id"),
    statuses: status && clusterStatuses.includes(status) ? [status] : [],
    topicName: params.get("topic_name"),
    learningObjectTypes:
      objectType && learningObjectTypes.includes(objectType)
        ? [objectType]
        : [],
    minDistinctInterviews: nullablePositiveInt(
      params.get("min_distinct_interviews"),
    ),
    minDistinctCompanies: nullablePositiveInt(
      params.get("min_distinct_companies"),
    ),
    hasFailedAnswers: params.get("has_failed_answers") === "true" ? true : null,
    minConfidence: nullableConfidence(params.get("min_confidence")),
    maxConfidence: nullableConfidence(params.get("max_confidence")),
    hasPossibleDuplicate:
      params.get("has_possible_duplicate") === "true" ? true : null,
    decisionSource:
      decisionSource && decisionSources.includes(decisionSource)
        ? decisionSource
        : null,
    seenFrom: seenFrom ? `${seenFrom}T00:00:00.000Z` : null,
    seenTo: seenTo ? `${seenTo}T23:59:59.999Z` : null,
    needsActionOnly: params.get("needs_action_only") !== "false",
    sortBy:
      sortBy && sortOptions.some((option) => option.value === sortBy)
        ? sortBy
        : "priority_score",
    sortOrder: params.get("sort_order") === "asc" ? "asc" : "desc",
  };
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString("ru-RU");
}

export function CardAutomationClustersPage({
  scope,
}: {
  scope: CardAutomationScope;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const parsedFilters = filtersFromParams(searchParams);
  const filters = {
    ...parsedFilters,
    directionId: scope === "admin" ? parsedFilters.directionId : null,
  };
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const query = useQuestionClusters(filters, page, scope);
  const tracks = useAdminTracks(scope === "admin");
  const [selected, setSelected] = useState<QuestionClusterSummary[]>([]);
  const [activeIndex, setActiveIndex] = useState(0);
  const items = query.data?.items ?? emptyClusters;
  const filterSearch = searchParams.toString();
  const detailBase = `/${scope}/card-automation/clusters`;

  useEffect(() => {
    setSelected([]);
    setActiveIndex(0);
  }, [filterSearch]);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        window.innerWidth < 768 ||
        event.metaKey ||
        event.ctrlKey ||
        event.altKey
      )
        return;
      const target = event.target;
      if (
        target instanceof HTMLElement &&
        target.closest(
          "input, textarea, select, button, a, [contenteditable='true']",
        )
      )
        return;
      if (event.key.toLocaleLowerCase("en-US") === "j") {
        event.preventDefault();
        setActiveIndex((current) => Math.min(items.length - 1, current + 1));
      } else if (event.key.toLocaleLowerCase("en-US") === "k") {
        event.preventDefault();
        setActiveIndex((current) => Math.max(0, current - 1));
      } else if (event.key === "Enter" && items[activeIndex]) {
        event.preventDefault();
        void navigate({
          pathname: `${detailBase}/${items[activeIndex].id}`,
          search: filterSearch,
        });
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeIndex, detailBase, filterSearch, items, navigate]);

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

  if (query.isPending) {
    return <LoadingState label="Загружаем карточки на проверку…" />;
  }
  if (query.isError) {
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  }

  const pageCount = Math.max(
    1,
    Math.ceil(query.data.total / CARD_AUTOMATION_PAGE_SIZE),
  );
  const selectedIds = new Set(selected.map((cluster) => cluster.id));
  const allPageSelected =
    items.length > 0 && items.every((cluster) => selectedIds.has(cluster.id));

  return (
    <Stack gap="xl">
      <PageHeader
        eyebrow={
          scope === "admin"
            ? "Администрирование · автоматизация карточек"
            : "Менторство · модерация своих направлений"
        }
        title="Карточки на проверку"
        description={
          scope === "admin"
            ? "Откройте предложение AI и проверьте четыре вещи: широкую тему, формулировку вопроса, готовый ответ и возможный дубль в базе. Всё можно исправить до публикации."
            : "Проверьте предложения AI по своим направлениям: тему, формулировку, ответ и возможное совпадение с существующей карточкой."
        }
      />
      <CardAutomationNavigation scope={scope} />

      <Card withBorder>
        <Stack>
          <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }}>
            {scope === "admin" && (
              <Select
                label="Направление"
                placeholder="Все направления"
                clearable
                searchable
                disabled={tracks.isPending || tracks.isError}
                value={filters.directionId}
                data={(tracks.data ?? []).map((track) => ({
                  value: track.id,
                  label: track.title,
                }))}
                onChange={(value) => updateFilter("direction_id", value)}
              />
            )}
            <Select
              label="Статус"
              value={filters.statuses[0] ?? "all"}
              data={[
                { value: "all", label: "Все статусы" },
                ...clusterStatuses.map((status) => ({
                  value: status,
                  label: clusterStatusLabels[status],
                })),
              ]}
              onChange={(value) =>
                updateFilter("status", value === "all" ? null : value)
              }
            />
            <TextInput
              label="Тема"
              placeholder="Например, Python core"
              value={searchParams.get("topic_name") ?? ""}
              onChange={(event) =>
                updateFilter("topic_name", event.currentTarget.value)
              }
            />
            <Select
              label="Тип учебного объекта"
              value={filters.learningObjectTypes[0] ?? "all"}
              data={[
                { value: "all", label: "Все типы" },
                ...learningObjectTypes.map((type) => ({
                  value: type,
                  label: learningObjectLabels[type],
                })),
              ]}
              onChange={(value) =>
                updateFilter(
                  "learning_object_type",
                  value === "all" ? null : value,
                )
              }
            />
            <NumberInput
              label="Минимум интервью"
              min={1}
              value={filters.minDistinctInterviews ?? ""}
              onChange={(value) =>
                updateFilter(
                  "min_distinct_interviews",
                  typeof value === "number" ? String(value) : null,
                )
              }
            />
            <NumberInput
              label="Минимум компаний"
              min={1}
              value={filters.minDistinctCompanies ?? ""}
              onChange={(value) =>
                updateFilter(
                  "min_distinct_companies",
                  typeof value === "number" ? String(value) : null,
                )
              }
            />
            <NumberInput
              label="Confidence от"
              min={0}
              max={1}
              step={0.05}
              decimalScale={2}
              value={filters.minConfidence ?? ""}
              onChange={(value) =>
                updateFilter(
                  "min_confidence",
                  typeof value === "number" ? String(value) : null,
                )
              }
            />
            <NumberInput
              label="Confidence до"
              min={0}
              max={1}
              step={0.05}
              decimalScale={2}
              value={filters.maxConfidence ?? ""}
              onChange={(value) =>
                updateFilter(
                  "max_confidence",
                  typeof value === "number" ? String(value) : null,
                )
              }
            />
            <Select
              label="Источник решения"
              placeholder="Любой"
              clearable
              value={filters.decisionSource}
              data={decisionSources.map((source) => ({
                value: source,
                label: decisionSourceLabels[source],
              }))}
              onChange={(value) => updateFilter("decision_source", value)}
            />
            <TextInput
              type="date"
              label="Встречался с"
              value={searchParams.get("seen_from") ?? ""}
              onChange={(event) =>
                updateFilter("seen_from", event.currentTarget.value)
              }
            />
            <TextInput
              type="date"
              label="Встречался до"
              value={searchParams.get("seen_to") ?? ""}
              onChange={(event) =>
                updateFilter("seen_to", event.currentTarget.value)
              }
            />
            <Group grow align="flex-end">
              <Select
                label="Сортировка"
                value={filters.sortBy}
                data={sortOptions}
                onChange={(value) => updateFilter("sort_by", value)}
              />
              <Select
                label="Порядок"
                value={filters.sortOrder}
                data={[
                  { value: "desc", label: "По убыванию" },
                  { value: "asc", label: "По возрастанию" },
                ]}
                onChange={(value) => updateFilter("sort_order", value)}
              />
            </Group>
            <Stack gap="xs" justify="flex-end">
              <Switch
                label="Только требующие решения"
                checked={filters.needsActionOnly}
                onChange={(event) =>
                  updateFilter(
                    "needs_action_only",
                    event.currentTarget.checked ? null : "false",
                  )
                }
              />
              <Switch
                label="Есть неуспешные ответы"
                checked={filters.hasFailedAnswers === true}
                onChange={(event) =>
                  updateFilter(
                    "has_failed_answers",
                    event.currentTarget.checked ? "true" : null,
                  )
                }
              />
              <Switch
                label="Есть возможный дубль"
                checked={filters.hasPossibleDuplicate === true}
                onChange={(event) =>
                  updateFilter(
                    "has_possible_duplicate",
                    event.currentTarget.checked ? "true" : null,
                  )
                }
              />
            </Stack>
            <Button
              variant="subtle"
              style={{ alignSelf: "flex-end" }}
              onClick={() => setSearchParams({}, { replace: true })}
              disabled={searchParams.size === 0}
            >
              Сбросить фильтры
            </Button>
          </SimpleGrid>
          {query.isFetching && !query.isPending && (
            <Text size="xs" c="dimmed" role="status">
              Обновляем результаты…
            </Text>
          )}
        </Stack>
      </Card>

      <Group justify="space-between">
        <Text fw={600}>Карточек требуют внимания: {query.data.total}</Text>
        <Stack gap={2} align="flex-end">
          <Text size="sm" c="dimmed">
            Новые карточки всегда подтверждает администратор
          </Text>
          <Text size="xs" c="dimmed" visibleFrom="sm">
            Клавиши J/K — строка, Enter — открыть
          </Text>
        </Stack>
      </Group>

      {scope === "admin" && (
        <ClusterBulkActions
          selected={selected}
          clearSelection={() => setSelected([])}
          reload={() => query.refetch()}
        />
      )}

      {query.data.items.length === 0 ? (
        <Card withBorder>
          <Text fw={600}>Карточек на проверку нет</Text>
          <Text size="sm" c="dimmed" mt={4}>
            Измените фильтры или дождитесь новых повторяющихся вопросов.
          </Text>
        </Card>
      ) : (
        <Card withBorder p={0}>
          <Table.ScrollContainer minWidth={1780}>
            <Table verticalSpacing="sm" horizontalSpacing="md" stickyHeader>
              <Table.Thead>
                <Table.Tr>
                  {scope === "admin" && (
                    <Table.Th w={48}>
                      <Checkbox
                        aria-label="Выбрать все кластеры на странице"
                        checked={allPageSelected}
                        indeterminate={selected.length > 0 && !allPageSelected}
                        onChange={(event) => {
                          const checked = event.currentTarget.checked;
                          setSelected(checked ? items : []);
                        }}
                      />
                    </Table.Th>
                  )}
                  <Table.Th>Предложение AI</Table.Th>
                  <Table.Th>Направление и тип</Table.Th>
                  <Table.Th>Появления</Table.Th>
                  <Table.Th>Интервью</Table.Th>
                  <Table.Th>Компании</Table.Th>
                  <Table.Th>Плохие ответы</Table.Th>
                  <Table.Th>Лучшее совпадение</Table.Th>
                  <Table.Th>Semantic</Table.Th>
                  <Table.Th>Judge</Table.Th>
                  <Table.Th>Confidence</Table.Th>
                  <Table.Th>Priority</Table.Th>
                  <Table.Th>Первое / последнее</Table.Th>
                  <Table.Th>Статус</Table.Th>
                  <Table.Th aria-label="Действия" />
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {query.data.items.map((cluster, index) => (
                  <Table.Tr
                    key={cluster.id}
                    data-active={activeIndex === index || undefined}
                    aria-selected={activeIndex === index}
                    onMouseEnter={() => setActiveIndex(index)}
                    onFocus={() => setActiveIndex(index)}
                    style={{
                      background:
                        scope === "admin" && selectedIds.has(cluster.id)
                          ? "var(--mantine-color-blue-light)"
                          : activeIndex === index
                            ? "var(--mantine-color-default-hover)"
                            : undefined,
                    }}
                  >
                    {scope === "admin" && (
                      <Table.Td>
                        <Checkbox
                          aria-label={`Выбрать кластер: ${cluster.canonical_question}`}
                          checked={selectedIds.has(cluster.id)}
                          onChange={(event) => {
                            const checked = event.currentTarget.checked;
                            setSelected((current) =>
                              checked
                                ? current.some((item) => item.id === cluster.id)
                                  ? current
                                  : [...current, cluster]
                                : current.filter(
                                    (item) => item.id !== cluster.id,
                                  ),
                            );
                          }}
                        />
                      </Table.Td>
                    )}
                    <Table.Td miw={360}>
                      <Text fw={650}>{cluster.canonical_question}</Text>
                      <Text size="xs" c="dimmed">
                        {cluster.topic_name ?? "Тема не определена"}
                      </Text>
                      {cluster.manual_important && (
                        <Badge color="red" mt={5}>
                          Важный
                        </Badge>
                      )}
                    </Table.Td>
                    <Table.Td miw={190}>
                      <Text fw={600}>{cluster.direction_title}</Text>
                      <Text size="xs" c="dimmed">
                        {learningObjectLabels[cluster.learning_object_type]}
                      </Text>
                    </Table.Td>
                    <Table.Td>{cluster.occurrences_count}</Table.Td>
                    <Table.Td>{cluster.distinct_interviews_count}</Table.Td>
                    <Table.Td>{cluster.distinct_companies_count}</Table.Td>
                    <Table.Td>{cluster.failed_answers_count}</Table.Td>
                    <Table.Td miw={250}>
                      {cluster.best_match ? (
                        <Text size="sm" fw={600} lineClamp={2}>
                          {cluster.best_match.question_markdown}
                        </Text>
                      ) : (
                        <Text size="sm" c="dimmed">
                          Нет кандидата
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td>
                      {cluster.best_match
                        ? percent(cluster.best_match.semantic_score)
                        : "—"}
                    </Table.Td>
                    <Table.Td miw={150}>
                      {cluster.best_match?.judge_decision
                        ? judgeDecisionLabels[cluster.best_match.judge_decision]
                        : "—"}
                    </Table.Td>
                    <Table.Td>{percent(cluster.cluster_confidence)}</Table.Td>
                    <Table.Td>{cluster.priority_score.toFixed(2)}</Table.Td>
                    <Table.Td miw={140}>
                      <Text size="sm">{formatDate(cluster.first_seen_at)}</Text>
                      <Text size="xs" c="dimmed">
                        {formatDate(cluster.last_seen_at)}
                      </Text>
                    </Table.Td>
                    <Table.Td>
                      <Badge color={clusterStatusColors[cluster.status]}>
                        {clusterStatusLabels[cluster.status]}
                      </Badge>
                    </Table.Td>
                    <Table.Td>
                      <Button
                        component={Link}
                        to={{
                          pathname: `${detailBase}/${cluster.id}`,
                          search: filterSearch,
                        }}
                        size="xs"
                        variant="light"
                      >
                        Проверить карточку
                      </Button>
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
    </Stack>
  );
}

export function AdminCardAutomationClustersPage() {
  return <CardAutomationClustersPage scope="admin" />;
}
