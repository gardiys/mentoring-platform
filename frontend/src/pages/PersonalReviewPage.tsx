import {
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Pagination,
  SimpleGrid,
  Stack,
  Switch,
  Text,
  Title,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import {
  CARD_AUTOMATION_PAGE_SIZE,
  usePersonalReviewItems,
  useReviewPersonalReviewItem,
} from "../features/cardAutomation/queries";
import { personalReviewStatusLabels } from "../features/cardAutomation/presentation";
import type {
  InterviewReviewRating,
  PersonalReviewFilters,
} from "../types/api";

const ratings: Array<{
  rating: InterviewReviewRating;
  label: string;
  hint: string;
  color: string;
}> = [
  { rating: "again", label: "Не помню", hint: "Повторить скоро", color: "red" },
  {
    rating: "hard",
    label: "Сложно",
    hint: "Нужен частый повтор",
    color: "orange",
  },
  { rating: "good", label: "Помню", hint: "Обычный интервал", color: "blue" },
  {
    rating: "easy",
    label: "Легко",
    hint: "Увеличить интервал",
    color: "green",
  },
];

function sourceLink(url: string) {
  if (/^https?:\/\//i.test(url)) {
    return (
      <Anchor href={url} target="_blank" rel="noreferrer" size="sm">
        Открыть исходный разбор ↗
      </Anchor>
    );
  }
  if (!url.startsWith("/")) return null;
  return (
    <Anchor component={Link} to={url} size="sm">
      Открыть исходный разбор →
    </Anchor>
  );
}

export function PersonalReviewPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(1, Number(searchParams.get("page")) || 1);
  const dueOnly = searchParams.get("due_only") !== "false";
  const filters: PersonalReviewFilters = {
    directionId: null,
    statuses: ["active"],
    dueOnly,
    dueBefore: null,
    sortOrder: "asc",
  };
  const query = usePersonalReviewItems(filters, page);
  const review = useReviewPersonalReviewItem();
  const [revealedItemId, setRevealedItemId] = useState<string | null>(null);

  const updatePage = (value: number) => {
    setSearchParams(
      (current) => {
        const next = new URLSearchParams(current);
        if (value > 1) next.set("page", String(value));
        else next.delete("page");
        return next;
      },
      { replace: true },
    );
  };

  if (query.isPending) return <LoadingState label="Готовим личные вопросы…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );

  const item = query.data.items[0];
  const revealed = item?.id === revealedItemId;
  const conflict =
    review.error instanceof ApiError && review.error.status === 409;
  const pageCount = Math.max(
    1,
    Math.ceil(query.data.total / CARD_AUTOMATION_PAGE_SIZE),
  );

  const rate = (rating: InterviewReviewRating) => {
    if (!item || review.isPending || !revealed) return;
    review.mutate(
      {
        itemId: item.id,
        payload: { rating, expected_version: item.version },
      },
      {
        onSuccess: (result) => {
          setRevealedItemId(null);
          notifications.show({
            color: "green",
            message: result.became_mastered
              ? "Вопрос освоен и убран из активного повторения"
              : "Ответ сохранён, следующий повтор запланирован",
          });
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-end">
        <PageHeader
          eyebrow="Собеседования · персональная подготовка"
          title="Личные вопросы"
          description="Вопросы из ваших разборов, для которых общей проверенной карточки пока нет. Они видны только вам."
        />
        <Badge size="lg" variant="light">
          {query.data.total} к повторению
        </Badge>
      </Group>

      <Card withBorder>
        <Group justify="space-between">
          <Switch
            label="Только запланированные сейчас"
            checked={dueOnly}
            onChange={(event) => {
              setSearchParams(
                event.currentTarget.checked ? {} : { due_only: "false" },
                { replace: true },
              );
              setRevealedItemId(null);
            }}
          />
          <Button component={Link} to="/interviews" variant="subtle">
            Все карточки
          </Button>
        </Group>
      </Card>

      {review.error && (
        <Alert
          color={conflict ? "yellow" : "red"}
          title={
            conflict
              ? "Этот вопрос уже был обновлён"
              : "Не удалось сохранить повторение"
          }
        >
          <Stack align="flex-start" gap="sm">
            <Text>{review.error.message}</Text>
            {conflict && (
              <Button
                variant="light"
                onClick={() => {
                  if (
                    window.confirm(
                      "Загрузить актуальное состояние вопроса и сбросить открытый ответ?",
                    )
                  ) {
                    review.reset();
                    setRevealedItemId(null);
                    void query.refetch();
                  }
                }}
              >
                Обновить вопрос
              </Button>
            )}
          </Stack>
        </Alert>
      )}

      {!item ? (
        <Card withBorder>
          <Stack align="center" ta="center" py="xl">
            <Text fz="2.5rem">✓</Text>
            <Title order={2}>
              {dueOnly ? "На сейчас всё" : "Личных вопросов пока нет"}
            </Title>
            <Text c="dimmed" maw={620}>
              {dueOnly
                ? "Все запланированные вопросы повторены. Можно посмотреть будущие, отключив фильтр выше."
                : "Они появятся, если в разборе собеседования найдётся плохо отвеченный технический вопрос без общей карточки."}
            </Text>
          </Stack>
        </Card>
      ) : (
        <Stack gap="md">
          <Group justify="space-between">
            <Group>
              <Badge>{item.direction_title}</Badge>
              <Badge variant="outline">
                {personalReviewStatusLabels[item.status]}
              </Badge>
            </Group>
            <Text className="technical-label">
              Успешных повторов: {item.successful_reviews_count}
            </Text>
          </Group>

          {item.replaced_by_card_id && (
            <Alert color="green" title="Появилась общая карточка">
              Этот личный вопрос заменён проверенной канонической карточкой и
              больше не должен создавать отдельное повторение.
            </Alert>
          )}

          <Card withBorder className="interview-study-card">
            <Stack justify="space-between" mih={380}>
              <div className="markdown-content interview-question">
                <ReactMarkdown>{item.question_text}</ReactMarkdown>
              </div>

              {!revealed ? (
                <Button size="xl" onClick={() => setRevealedItemId(item.id)}>
                  Показать ответ
                </Button>
              ) : (
                <Stack>
                  <Card withBorder bg="var(--mantine-color-default-hover)">
                    <Stack>
                      <div className="markdown-content">
                        <ReactMarkdown>
                          {item.answer_contract?.short_answer ??
                            item.answer_summary ??
                            "Проверенного краткого ответа пока нет."}
                        </ReactMarkdown>
                      </div>
                      {item.answer_contract && (
                        <>
                          <Text fw={700}>Что обязательно упомянуть</Text>
                          {item.answer_contract.required_points.length === 0 ? (
                            <Text size="sm" c="dimmed">
                              Обязательные пункты не выделены.
                            </Text>
                          ) : (
                            item.answer_contract.required_points.map(
                              (point) => (
                                <Text key={point} size="sm">
                                  • {point}
                                </Text>
                              ),
                            )
                          )}
                          {item.answer_contract.common_mistakes.length > 0 && (
                            <Alert color="yellow" title="Типичные ошибки">
                              {item.answer_contract.common_mistakes.join("; ")}
                            </Alert>
                          )}
                        </>
                      )}
                    </Stack>
                  </Card>

                  <SimpleGrid cols={{ base: 1, sm: 2, lg: 4 }}>
                    {ratings.map((rating) => (
                      <Button
                        key={rating.rating}
                        color={rating.color}
                        variant="light"
                        h="auto"
                        py="md"
                        loading={
                          review.isPending &&
                          review.variables?.payload.rating === rating.rating
                        }
                        disabled={review.isPending}
                        onClick={() => rate(rating.rating)}
                      >
                        <Stack gap={2} align="center">
                          <Text fw={700}>{rating.label}</Text>
                          <Text size="xs">{rating.hint}</Text>
                        </Stack>
                      </Button>
                    ))}
                  </SimpleGrid>
                </Stack>
              )}
            </Stack>
          </Card>

          <Group justify="space-between">
            <Text size="sm" c="dimmed">
              Запланировано: {new Date(item.due_at).toLocaleString("ru-RU")}
            </Text>
            {item.source_analysis_url && sourceLink(item.source_analysis_url)}
          </Group>
        </Stack>
      )}

      {pageCount > 1 && (
        <Pagination
          value={page}
          total={pageCount}
          disabled={query.isPlaceholderData || review.isPending}
          onChange={updatePage}
          mx="auto"
        />
      )}
    </Stack>
  );
}
