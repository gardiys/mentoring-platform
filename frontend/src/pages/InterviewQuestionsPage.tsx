import {
  Anchor,
  Badge,
  Card,
  Checkbox,
  Group,
  Pagination,
  SegmentedControl,
  Select,
  Stack,
  Switch,
  Table,
  Text,
  TextInput,
  Title,
  UnstyledButton,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { Fragment, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { InterviewQuestionModeNavigation } from "../features/interviews/InterviewQuestionModeNavigation";
import {
  useInterviewQuestionTable,
  useInterviewTopics,
  useSetInterviewQuestionLearned,
} from "../features/interviews/queries";
import type {
  InterviewQuestionLearnedFilter,
  InterviewQuestionTableItem,
} from "../types/api";

const PAGE_SIZE = 25;

function plainText(markdown: string) {
  return markdown
    .replace(/[`*_>#]/g, "")
    .replace(/\[(.*?)\]\(.*?\)/g, "$1")
    .replace(/\s+/g, " ")
    .trim();
}

function readableDate(value: string) {
  return new Date(value).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export function InterviewQuestionsPage() {
  const { deckSlug = "" } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [expandedAnswers, setExpandedAnswers] = useState<Set<string>>(
    () => new Set(),
  );
  const searchText = searchParams.get("q") ?? "";
  const [debouncedSearch] = useDebouncedValue(searchText.trim(), 300);
  const category = searchParams.get("category");
  const frequentOnly = searchParams.get("frequent_only") === "true";
  const learnedParam = searchParams.get("learned");
  const learned: InterviewQuestionLearnedFilter =
    learnedParam === "learned" || learnedParam === "unlearned"
      ? learnedParam
      : "all";
  const requestedPage = Number(searchParams.get("page") ?? "1");
  const page =
    Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  const topics = useInterviewTopics(deckSlug);
  const questions = useInterviewQuestionTable(deckSlug, {
    category,
    frequentOnly,
    learned,
    query: debouncedSearch,
    limit: PAGE_SIZE,
    offset: (page - 1) * PAGE_SIZE,
  });
  const learnedMutation = useSetInterviewQuestionLearned();

  const setFilter = (key: string, value: string | null) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value) next.set(key, value);
        else next.delete(key);
        if (key !== "page") next.delete("page");
        return next;
      },
      { replace: true },
    );
  };

  if (topics.isPending || questions.isPending) {
    return <LoadingState label="Загружаем таблицу вопросов…" />;
  }
  if (topics.isError || questions.isError) {
    return (
      <ErrorState
        error={topics.error ?? questions.error}
        retry={() => {
          void topics.refetch();
          void questions.refetch();
        }}
      />
    );
  }

  const { deck, items, total } = questions.data;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const toggleAnswer = (cardId: string) => {
    setExpandedAnswers((current) => {
      const next = new Set(current);
      if (next.has(cardId)) next.delete(cardId);
      else next.add(cardId);
      return next;
    });
  };

  const toggleLearned = (
    item: InterviewQuestionTableItem,
    checked: boolean,
  ) => {
    learnedMutation.mutate(
      { cardId: item.id, learned: checked },
      {
        onSuccess: () =>
          notifications.show({
            color: checked ? "green" : "blue",
            message: checked
              ? "Вопрос отмечен выученным. Следующий повтор — через месяц."
              : "Отметка снята. Вопрос снова попадёт в обучение.",
          }),
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Stack gap="xl">
      <div>
        <Anchor component={Link} to="/interviews" size="sm">
          ← Все разделы собеседований
        </Anchor>
        <Group justify="space-between" align="flex-end" mt="md">
          <div>
            <Text className="brand-eyebrow">
              {deck.track_title} · база вопросов
            </Text>
            <Title order={1}>{deck.title}</Title>
          </div>
          <Badge size="lg" variant="light">
            Найдено: {total}
          </Badge>
        </Group>
      </div>

      <InterviewQuestionModeNavigation deckSlug={deckSlug} mode="table" />

      <Card withBorder className="interview-question-filters">
        <Stack gap="md">
          <TextInput
            label="Поиск вопроса"
            placeholder="Например: индексы PostgreSQL"
            value={searchText}
            onChange={(event) =>
              setFilter("q", event.currentTarget.value || null)
            }
          />
          <Group grow align="flex-end">
            <Select
              label="Тема"
              placeholder="Все выбранные темы"
              clearable
              searchable
              value={category}
              data={topics.data.map((topic) => topic.name)}
              onChange={(value) => setFilter("category", value)}
            />
            <div>
              <Text size="sm" fw={500} mb={6}>
                Статус изучения
              </Text>
              <SegmentedControl
                fullWidth
                value={learned}
                data={[
                  { value: "all", label: "Все" },
                  { value: "unlearned", label: "Не выучены" },
                  { value: "learned", label: "Выучены" },
                ]}
                onChange={(value) =>
                  setFilter("learned", value === "all" ? null : value)
                }
              />
            </div>
          </Group>
          <Switch
            label="Только частые вопросы"
            description="Показывать в первую очередь то, что чаще спрашивают на собеседованиях"
            checked={frequentOnly}
            onChange={(event) =>
              setFilter(
                "frequent_only",
                event.currentTarget.checked ? "true" : null,
              )
            }
          />
        </Stack>
      </Card>

      {items.length === 0 ? (
        <Card withBorder>
          <Stack align="center" ta="center" py="xl">
            <Title order={2}>Вопросы не найдены</Title>
            <Text c="dimmed">
              Попробуйте изменить тему, статус изучения, поиск или фильтр частых
              вопросов.
            </Text>
          </Stack>
        </Card>
      ) : (
        <Card withBorder p={0} className="interview-question-table-card">
          <Table.ScrollContainer minWidth={860}>
            <Table verticalSpacing="md" horizontalSpacing="md" highlightOnHover>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th w={100}>Выучен</Table.Th>
                  <Table.Th>Вопрос</Table.Th>
                  <Table.Th w={240}>Тема</Table.Th>
                  <Table.Th w={140}>Частота</Table.Th>
                  <Table.Th w={180}>Повторение</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {items.map((item) => {
                  const answerExpanded = expandedAnswers.has(item.id);
                  const answerId = `interview-question-answer-${item.id}`;
                  return (
                    <Fragment key={item.id}>
                      <Table.Tr
                        className={
                          item.learned
                            ? "interview-question-row--learned"
                            : undefined
                        }
                      >
                        <Table.Td>
                          <Checkbox
                            aria-label={`Отметить выученным: ${plainText(item.question_markdown)}`}
                            checked={item.learned}
                            disabled={learnedMutation.isPending}
                            color="green"
                            size="lg"
                            onChange={(event) =>
                              toggleLearned(item, event.currentTarget.checked)
                            }
                          />
                        </Table.Td>
                        <Table.Td>
                          <UnstyledButton
                            className="interview-question-table-toggle"
                            aria-expanded={answerExpanded}
                            aria-controls={answerId}
                            onClick={() => toggleAnswer(item.id)}
                          >
                            <Stack gap={5}>
                              <Text fw={650}>
                                {plainText(item.question_markdown)}
                              </Text>
                              <Group gap="xs">
                                <Text size="sm" c="brandBlue" fw={650}>
                                  {answerExpanded
                                    ? "Скрыть ответ ↑"
                                    : "Показать ответ ↓"}
                                </Text>
                                {item.learned && (
                                  <Badge color="green" variant="light">
                                    Выучен
                                  </Badge>
                                )}
                              </Group>
                            </Stack>
                          </UnstyledButton>
                        </Table.Td>
                        <Table.Td>
                          <Text fw={600}>{item.category}</Text>
                          {item.subcategory && (
                            <Text size="sm" c="dimmed">
                              {item.subcategory}
                            </Text>
                          )}
                        </Table.Td>
                        <Table.Td>
                          <Badge
                            color={
                              item.frequency === "frequent"
                                ? "brandYellow"
                                : "gray"
                            }
                            c={
                              item.frequency === "frequent"
                                ? "brandNavy.9"
                                : undefined
                            }
                          >
                            {item.frequency === "frequent"
                              ? "Частый"
                              : "Редкий"}
                          </Badge>
                        </Table.Td>
                        <Table.Td>
                          {item.learned && item.due_at ? (
                            <Stack gap={2}>
                              <Text size="sm" fw={600}>
                                {readableDate(item.due_at)}
                              </Text>
                              <Text size="xs" c="dimmed">
                                Повторов: {item.repetitions}
                              </Text>
                            </Stack>
                          ) : (
                            <Text size="sm" c="dimmed">
                              Ещё не изучался
                            </Text>
                          )}
                        </Table.Td>
                      </Table.Tr>
                      {answerExpanded && (
                        <Table.Tr className="interview-question-answer-row">
                          <Table.Td colSpan={5} id={answerId}>
                            <div className="interview-question-table-answer">
                              <Text className="technical-label" mb="xs">
                                Ответ
                              </Text>
                              <div className="markdown-content">
                                <ReactMarkdown>
                                  {item.answer_markdown}
                                </ReactMarkdown>
                              </div>
                            </div>
                          </Table.Td>
                        </Table.Tr>
                      )}
                    </Fragment>
                  );
                })}
              </Table.Tbody>
            </Table>
          </Table.ScrollContainer>
        </Card>
      )}

      {totalPages > 1 && (
        <Group justify="center">
          <Pagination
            value={Math.min(page, totalPages)}
            total={totalPages}
            onChange={(value) => setFilter("page", String(value))}
          />
        </Group>
      )}
    </Stack>
  );
}
