import { CardGridSkeleton } from "../components/CardGridSkeleton";
import {
  Accordion,
  Alert,
  Anchor,
  Badge,
  Button,
  Card,
  Group,
  Progress,
  Stack,
  Switch,
  Text,
  TextInput,
  Title,
} from "@mantine/core";
import { useDebouncedValue } from "@mantine/hooks";
import { notifications } from "@mantine/notifications";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Link, useParams, useSearchParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { InterviewTopicSelector } from "../features/interviews/InterviewTopicSelector";
import { InterviewQuestionModeNavigation } from "../features/interviews/InterviewQuestionModeNavigation";
import {
  useInterviewCardSearch,
  useInterviewSession,
  useInterviewTopics,
  useReviewInterviewCard,
} from "../features/interviews/queries";
import type { InterviewReviewRating } from "../types/api";

const ratings: Array<{
  rating: InterviewReviewRating;
  label: string;
  hint: string;
  color: string;
}> = [
  {
    rating: "again",
    label: "Не помню",
    hint: "10 минут",
    color: "red",
  },
  {
    rating: "hard",
    label: "Сложно",
    hint: "1 день",
    color: "orange",
  },
  {
    rating: "good",
    label: "Помню",
    hint: "~2 дня",
    color: "brandBlue",
  },
  {
    rating: "easy",
    label: "Легко",
    hint: "~4 дня",
    color: "green",
  },
  {
    rating: "known",
    label: "Знаю",
    hint: "1 месяц",
    color: "teal",
  },
];

function questionPreview(markdown: string) {
  return markdown
    .replace(/[`*_>#]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

export function InterviewStudyPage() {
  const { deckSlug = "" } = useParams();
  const studyCard = useRef<HTMLDivElement>(null);
  const previousReveal = useRef<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const frequentOnly = searchParams.get("frequent_only") === "true";
  const searchText = searchParams.get("q") ?? "";
  const [debouncedSearch] = useDebouncedValue(searchText.trim(), 300);
  const query = useInterviewSession(deckSlug, frequentOnly);
  const topics = useInterviewTopics(deckSlug);
  const search = useInterviewCardSearch(
    deckSlug,
    debouncedSearch,
    frequentOnly,
  );
  const review = useReviewInterviewCard();
  const [revealedCardId, setRevealedCardId] = useState<string | null>(null);

  useEffect(() => {
    if (previousReveal.current === revealedCardId) return;
    previousReveal.current = revealedCardId;
    studyCard.current?.scrollIntoView?.({ block: "start" });
  }, [revealedCardId]);

  if (query.isPending || topics.isPending) {
    return <LoadingState label="Готовим учебную сессию…" />;
  }
  if (query.isError || topics.isError) {
    return (
      <ErrorState
        error={query.error ?? topics.error}
        retry={() => {
          void query.refetch();
          void topics.refetch();
        }}
      />
    );
  }

  const { deck, cards } = query.data;
  const card = cards[0];
  const revealed = card?.id === revealedCardId;

  const rate = (rating: InterviewReviewRating) => {
    if (!card || review.isPending || query.isPlaceholderData) return;
    review.mutate(
      { cardId: card.id, rating },
      {
        onSuccess: () => {
          setRevealedCardId(null);
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Stack gap="xl">
      <div>
        <Anchor component={Link} to="/interviews" size="sm">
          ← Все колоды
        </Anchor>
        <Group justify="space-between" align="flex-end" mt="md">
          <div>
            <Text className="brand-eyebrow">
              {deck.track_title} · тренировка
            </Text>
            <Title order={1}>{deck.title}</Title>
          </div>
          <Badge size="lg" variant="light">
            {deck.stats.selected_categories > 0
              ? `Осталось ${deck.stats.remaining_cards}`
              : "Темы не выбраны"}
          </Badge>
        </Group>
        <Progress
          aria-label="Прогресс повторения карточек"
          value={deck.stats.progress_percent}
          mt="md"
          size="lg"
          radius="xl"
        />
      </div>

      <InterviewQuestionModeNavigation deckSlug={deckSlug} mode="study" />

      <InterviewTopicSelector deckSlug={deckSlug} topics={topics.data} />

      <Card withBorder>
        <Stack gap="md">
          <TextInput
            label="Поиск по карточкам"
            description="Ищет по вопросам, ответам и выбранным темам, включая уже изученные карточки"
            placeholder="Например: индексы в PostgreSQL"
            value={searchText}
            onChange={(event) => {
              const value = event.currentTarget.value;
              setSearchParams(
                (current) => {
                  const next = new URLSearchParams(current);
                  if (value) next.set("q", value);
                  else next.delete("q");
                  return next;
                },
                { replace: true },
              );
              setRevealedCardId(null);
            }}
          />
          <Switch
            label="Только частые вопросы"
            description="Скрыть редкие вопросы из тренировки и результатов поиска"
            checked={frequentOnly}
            onChange={(event) => {
              const checked = event.currentTarget.checked;
              setSearchParams(
                (current) => {
                  const next = new URLSearchParams(current);
                  if (checked) next.set("frequent_only", "true");
                  else next.delete("frequent_only");
                  return next;
                },
                { replace: true },
              );
              setRevealedCardId(null);
            }}
          />
        </Stack>
      </Card>

      {review.isError && (
        <Alert color="red" title="Не удалось сохранить ответ">
          {review.error.message}
        </Alert>
      )}

      {searchText.trim().length === 1 ? (
        <Alert color="blue" title="Введи ещё один символ">
          Поиск начинается с двух символов.
        </Alert>
      ) : debouncedSearch.length >= 2 ? (
        search.isPending ? (
          <LoadingState label="Ищем карточки…" />
        ) : search.isError ? (
          <ErrorState
            error={search.error}
            retry={() => void search.refetch()}
          />
        ) : search.data.length === 0 ? (
          <Card withBorder>
            <Stack align="center" ta="center">
              <Title order={2}>Ничего не найдено</Title>
              <Text c="dimmed">
                Проверь формулировку, выбранные темы и фильтр частых вопросов.
              </Text>
            </Stack>
          </Card>
        ) : (
          <Stack gap="sm">
            <Group justify="space-between">
              <Title order={2}>Результаты поиска</Title>
              <Badge variant="light">Показано: {search.data.length}</Badge>
            </Group>
            <Accordion variant="separated">
              {search.data.map((item) => (
                <Accordion.Item key={item.id} value={item.id}>
                  <Accordion.Control>
                    <Group justify="space-between" wrap="nowrap" pr="sm">
                      <Text fw={650}>
                        {questionPreview(item.question_markdown)}
                      </Text>
                      {item.frequency === "frequent" && (
                        <Badge
                          color="brandYellow"

                          visibleFrom="sm"
                        >
                          Частый
                        </Badge>
                      )}
                    </Group>
                  </Accordion.Control>
                  <Accordion.Panel>
                    <Stack gap="md">
                      <Group gap="xs">
                        <Badge variant="light">{item.category}</Badge>
                        {item.subcategory && (
                          <Badge variant="outline">{item.subcategory}</Badge>
                        )}
                        {item.is_new && <Badge variant="outline">Новая</Badge>}
                      </Group>
                      <div className="markdown-content">
                        <ReactMarkdown>{item.question_markdown}</ReactMarkdown>
                      </div>
                      <Stack className="interview-answer">
                        <Text className="technical-label">Ответ</Text>
                        <div className="markdown-content">
                          <ReactMarkdown>{item.answer_markdown}</ReactMarkdown>
                        </div>
                      </Stack>
                      {item.companies && (
                        <Text size="sm" c="dimmed">
                          Встречался в компаниях: {item.companies}
                        </Text>
                      )}
                    </Stack>
                  </Accordion.Panel>
                </Accordion.Item>
              ))}
            </Accordion>
          </Stack>
        )
      ) : query.isPlaceholderData ? (
        <CardGridSkeleton />
      ) : deck.stats.selected_categories === 0 ? (
        <Card withBorder className="interview-complete-card">
          <Stack align="center" ta="center">
            <Text fz="2.5rem">↑</Text>
            <Title order={2}>Сначала выбери темы</Title>
            <Text c="dimmed" maw={560}>
              Отметь только пройденные разделы. Так в тренировке не появятся
              вопросы из тем, до которых ты ещё не дошли по роадмапу.
            </Text>
          </Stack>
        </Card>
      ) : !card ? (
        <Card withBorder className="interview-complete-card">
          <Stack align="center" ta="center">
            <Text fz="2.5rem">✓</Text>
            <Title order={2}>На сегодня всё</Title>
            <Text c="dimmed" maw={560}>
              Новых карточек и запланированных повторений сейчас нет.
              Возвращайся к ним по расписанию — так знания закрепляются лучше.
            </Text>
            <Button component={Link} to="/interviews" variant="light">
              Вернуться к колодам
            </Button>
          </Stack>
        </Card>
      ) : (
        <Stack gap="md">
          <Group justify="space-between">
            <Group>
              <Badge
                color={
                  card.frequency === "frequent" ? "brandYellow" : "brandSand"
                }
              >
                {card.frequency === "frequent"
                  ? "Частый вопрос"
                  : "Редкий вопрос"}
              </Badge>
              {card.category && <Badge variant="light">{card.category}</Badge>}
              {card.subcategory && (
                <Badge variant="outline">{card.subcategory}</Badge>
              )}
              {card.is_new && <Badge variant="outline">Новая</Badge>}
            </Group>
            <Text className="technical-label">В сессии: {cards.length}</Text>
          </Group>

          <Card ref={studyCard} withBorder className="interview-study-card">
            <Stack justify="space-between" h="100%">
              <div className="markdown-content interview-question">
                <ReactMarkdown>{card.question_markdown}</ReactMarkdown>
              </div>
              {!revealed ? (
                <Button
                  size="xl"
                  onClick={() => {
                    setRevealedCardId(card.id);
                  }}
                  className="reveal-answer-button"
                >
                  Показать ответ
                </Button>
              ) : (
                <Stack className="interview-answer" aria-live="polite">
                  <Text className="technical-label">
                    Обратная сторона · ответ
                  </Text>
                  <div className="markdown-content">
                    <ReactMarkdown>{card.answer_markdown}</ReactMarkdown>
                  </div>
                  {card.companies && (
                    <Text size="sm" c="dimmed">
                      Встречался в компаниях: {card.companies}
                    </Text>
                  )}
                </Stack>
              )}
            </Stack>
          </Card>

          {revealed && (
            <div>
              <Text ta="center" c="dimmed" mb="sm">
                Насколько легко ты вспомнил ответ?
              </Text>
              <div className="interview-rating-grid">
                {ratings.map((item) => (
                  <Button
                    key={item.rating}
                    aria-label={
                      item.rating === "known"
                        ? `Знаю отлично · ${item.hint}`
                        : undefined
                    }
                    color={item.color}
                    variant={item.rating === "good" ? "filled" : "light"}
                    loading={review.isPending}
                    size="xl"
                    onClick={() => rate(item.rating)}
                    className="interview-rating-button"
                  >
                    <Stack gap={0} align="center">
                      <span>{item.label}</span>
                      <Text component="span" size="sm" c="inherit" fw={400}>
                        {item.hint}
                      </Text>
                    </Stack>
                  </Button>
                ))}
              </div>
            </div>
          )}
        </Stack>
      )}
    </Stack>
  );
}
