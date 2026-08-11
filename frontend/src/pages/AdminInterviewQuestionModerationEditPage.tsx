import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Radio,
  Select,
  Stack,
  Switch,
  Text,
  Textarea,
  TextInput,
} from "@mantine/core";
import { notifications } from "@mantine/notifications";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { useUnsavedChanges } from "../hooks/useUnsavedChanges";
import {
  useAdminQuestionModerationDetail,
  useIntelligenceQuestionModeration,
} from "../features/interviews/intelligenceQueries";
import {
  intelligenceDifficultyLabels,
  intelligenceQuestionKindLabels,
} from "../features/interviews/intelligencePresentation";
import type {
  AdminQuestionModerationCardCandidate,
  AdminQuestionModerationDetail,
} from "../types/api";

const CREATE_NEW_CARD = "__create_new_card__";

function normalizeCategory(value: string) {
  return value
    .normalize("NFKC")
    .trim()
    .replace(/\s+/g, " ")
    .toLocaleLowerCase("ru-RU");
}

function matchingCategory(categories: string[], value: string) {
  const normalized = normalizeCategory(value);
  return (
    categories.find((category) => normalizeCategory(category) === normalized) ??
    null
  );
}

function questionPreview(value: string) {
  return value.replace(/^#{1,6}\s*/, "").trim();
}

function candidateMatchedText(
  candidate: AdminQuestionModerationCardCandidate,
): string {
  return typeof candidate.matched_text === "string"
    ? candidate.matched_text.trim()
    : "";
}

function moderationCandidates(
  item: AdminQuestionModerationDetail,
): AdminQuestionModerationCardCandidate[] {
  if ((item.card_candidates ?? []).length > 0) return item.card_candidates;
  if (
    !item.matched_card_id ||
    !item.matched_card_deck_id ||
    !item.matched_card_category ||
    !item.matched_card_question
  ) {
    return [];
  }
  return [
    {
      id: item.matched_card_id,
      deck_id: item.matched_card_deck_id,
      deck_title:
        item.deck_options.find(
          (option) => option.id === item.matched_card_deck_id,
        )?.title ?? "—",
      category: item.matched_card_category,
      question_markdown: item.matched_card_question,
      answer_markdown: item.matched_card_answer ?? "",
      matched_text: item.matched_card_question,
      asked_count: item.matched_card_asked_count ?? 0,
      frequency: "occasional",
      similarity: 1,
      match_type: "exact",
      matched_source: "card",
    },
  ];
}

function ModerationForm({ item }: { item: AdminQuestionModerationDetail }) {
  const navigate = useNavigate();
  const moderation = useIntelligenceQuestionModeration();
  const cardCandidates = moderationCandidates(item);
  const exactCardCandidate = cardCandidates.find(
    (candidate) =>
      candidate.match_type === "exact" && candidate.matched_source === "card",
  );
  const initialDestination = exactCardCandidate
    ? exactCardCandidate.id
    : cardCandidates.length === 0
      ? CREATE_NEW_CARD
      : null;
  const initialDeckId =
    item.matched_card_deck_id ?? item.deck_options[0]?.id ?? null;
  const initialDeck = item.deck_options.find(
    (option) => option.id === initialDeckId,
  );
  const initialCategory =
    item.matched_card_category ??
    matchingCategory(initialDeck?.categories ?? [], item.category);
  const [question, setQuestion] = useState(item.question_text);
  const newCardInitialAnswer =
    item.suggested_answer || item.candidate_answer || "";
  const initialAnswer =
    exactCardCandidate?.answer_markdown ?? newCardInitialAnswer;
  const [answer, setAnswer] = useState(initialAnswer);
  const [deckId, setDeckId] = useState<string | null>(initialDeckId);
  const [category, setCategory] = useState<string | null>(initialCategory);
  const [createCategory, setCreateCategory] = useState(false);
  const [newCategory, setNewCategory] = useState(item.category);
  const [destination, setDestination] = useState<string | null>(
    initialDestination,
  );
  const [frequencyMode, setFrequencyMode] = useState<"automatic" | "manual">(
    "automatic",
  );
  const [frequency, setFrequency] = useState<"frequent" | "occasional">(
    "occasional",
  );
  const selectedDeck = item.deck_options.find((option) => option.id === deckId);
  const targetCard = cardCandidates.find(
    (candidate) => candidate.id === destination,
  );
  const isCreateNew = destination === CREATE_NEW_CARD;
  const moderationCategory = createCategory ? newCategory.trim() : category;
  const allowNavigation = useUnsavedChanges(
    question !== item.question_text ||
      answer !== (item.suggested_answer || item.candidate_answer || "") ||
      destination !== initialDestination ||
      deckId !== initialDeckId ||
      category !== initialCategory ||
      createCategory ||
      frequencyMode !== "automatic" ||
      frequency !== "occasional",
  );

  const changeDeck = (value: string | null) => {
    const nextDeck = item.deck_options.find((option) => option.id === value);
    setDeckId(value);
    setCategory(matchingCategory(nextDeck?.categories ?? [], item.category));
    setCreateCategory(false);
  };

  const changeDestination = (value: string) => {
    setDestination(value);
    setAnswer(
      value === CREATE_NEW_CARD
        ? newCardInitialAnswer
        : (cardCandidates.find((candidate) => candidate.id === value)
            ?.answer_markdown ?? ""),
    );
  };

  const submit = (action: "approve" | "reject") => {
    if (
      action === "reject" &&
      !window.confirm(
        "Отклонить вопрос? Он не будет добавлен в общую базу карточек.",
      )
    )
      return;
    if (action === "approve" && !targetCard && !isCreateNew) return;

    const approvePayload = targetCard
      ? {
          action: "approve" as const,
          target_card_id: targetCard.id,
          question_markdown: question.trim(),
          answer_markdown: answer.trim(),
        }
      : {
          action: "approve" as const,
          question_markdown: question.trim(),
          answer_markdown: answer.trim(),
          deck_id: deckId ?? undefined,
          category: moderationCategory?.trim(),
          create_category: createCategory,
          create_new_card: true,
          frequency_mode: frequencyMode,
          ...(frequencyMode === "manual" ? { frequency } : {}),
        };
    moderation.mutate(
      {
        interviewId: item.interview_id,
        questionId: item.question_id,
        payload: action === "approve" ? approvePayload : { action },
      },
      {
        onSuccess: () => {
          allowNavigation();
          notifications.show({
            color: "green",
            message:
              action === "approve"
                ? "Вопрос учтён в базе карточек"
                : "Вопрос отклонён",
          });
          navigate("/admin/interview-question-moderation");
        },
        onError: (error) =>
          notifications.show({ color: "red", message: error.message }),
      },
    );
  };

  return (
    <Stack gap="xl">
      <Group justify="space-between" align="flex-start">
        <PageHeader
          eyebrow={`${item.track_title} · ${item.company_name}`}
          title="Проверка вопроса"
          description={`${item.student_name} · ${new Date(item.interviewed_at).toLocaleString("ru-RU")}`}
        />
        <Button
          component={Link}
          to="/admin/interview-question-moderation"
          variant="light"
        >
          К списку
        </Button>
      </Group>
      {cardCandidates.length > 0 && (
        <Card withBorder>
          <Stack gap="sm">
            <div>
              <Text fw={700}>Возможные совпадения</Text>
              <Text size="sm" c="dimmed">
                {exactCardCandidate
                  ? "Найдено точное совпадение с основной карточкой. Проверьте формулировку перед подтверждением."
                  : "Проверьте смысл вопроса и явно выберите существующую карточку или создание новой."}
              </Text>
            </div>
            <Radio.Group
              label="Что сделать с вопросом?"
              value={destination ?? ""}
              onChange={changeDestination}
            >
              <Stack mt="sm" gap="sm">
                {cardCandidates.map((candidate) => {
                  const matchedText = candidateMatchedText(candidate);
                  const matchedByAlias =
                    candidate.matched_source === "approved_alias";
                  return (
                    <Card
                      key={candidate.id}
                      withBorder
                      padding="sm"
                      bg={
                        destination === candidate.id
                          ? "var(--mantine-color-blue-light)"
                          : undefined
                      }
                    >
                      <Stack gap="xs">
                        <Radio
                          value={candidate.id}
                          label={`Связать с карточкой: ${questionPreview(candidate.question_markdown)}`}
                        />
                        <Group gap="xs" ml={30}>
                          <Badge
                            color={
                              candidate.match_type === "exact" ? "blue" : "gray"
                            }
                          >
                            {candidate.match_type === "exact"
                              ? matchedByAlias
                                ? "Точно совпало с подтверждённым вариантом"
                                : "Точное совпадение"
                              : `Похожий вопрос · ${Math.round(candidate.similarity * 100)}%`}
                          </Badge>
                          <Badge variant="light">
                            Спросили раз: {candidate.asked_count}
                          </Badge>
                          <Badge variant="outline">
                            {candidate.frequency === "frequent"
                              ? "Частый"
                              : "Обычный"}
                          </Badge>
                        </Group>
                        <Text size="sm" c="dimmed" ml={30}>
                          Набор: {candidate.deck_title} · Тема:{" "}
                          {candidate.category}
                          {matchedByAlias
                            ? " · совпало с ранее подтверждённой формулировкой"
                            : ""}
                        </Text>
                        {matchedByAlias && matchedText && (
                          <Text size="sm" ml={30}>
                            Совпавшая формулировка: «
                            {questionPreview(matchedText)}»
                          </Text>
                        )}
                        <Text
                          size="sm"
                          ml={30}
                          style={{ whiteSpace: "pre-wrap" }}
                          lineClamp={4}
                        >
                          <Text component="span" fw={600}>
                            Ответ карточки:{" "}
                          </Text>
                          {candidate.answer_markdown}
                        </Text>
                      </Stack>
                    </Card>
                  );
                })}
                {!exactCardCandidate && (
                  <Radio
                    value={CREATE_NEW_CARD}
                    label="Создать новую карточку, это другой вопрос"
                  />
                )}
              </Stack>
            </Radio.Group>
            {!destination && (
              <Alert color="yellow" title="Нужно выбрать действие">
                Похожие вопросы не объединяются автоматически. Сравните
                формулировки и подтвердите решение.
              </Alert>
            )}
          </Stack>
        </Card>
      )}
      {targetCard && (
        <Alert
          color="blue"
          title={
            targetCard.match_type === "exact"
              ? "Найдена существующая карточка"
              : "Выбрана существующая карточка"
          }
        >
          После подтверждения новая карточка не создастся: для «
          {questionPreview(targetCard.question_markdown)}» появление будет
          учтено. Счётчик увеличится, если это первое совпадение в данном
          собеседовании.
        </Alert>
      )}
      {isCreateNew && item.deck_options.length === 0 && (
        <Alert color="red" title="Нет опубликованных наборов карточек">
          Сначала опубликуйте хотя бы один набор для направления «
          {item.track_title}».
        </Alert>
      )}
      <Card withBorder>
        <Stack>
          <Group>
            <Badge>{intelligenceQuestionKindLabels[item.question_kind]}</Badge>
            <Badge variant="outline">
              {intelligenceDifficultyLabels[item.difficulty]}
            </Badge>
          </Group>
          <Textarea
            label="Вопрос"
            value={question}
            onChange={(event) => setQuestion(event.currentTarget.value)}
            minRows={3}
            required
            description={
              targetCard
                ? "Исправленная формулировка сохранится как подтверждённый вариант вопроса. Существующая карточка не изменится."
                : undefined
            }
          />
          <Textarea
            label={
              targetCard
                ? "Ответ связанной карточки"
                : "Проверенный ответ для обратной стороны карточки"
            }
            description={
              targetCard
                ? "При подтверждении изменённый ответ сохранится в существующей карточке."
                : undefined
            }
            value={answer}
            onChange={(event) => setAnswer(event.currentTarget.value)}
            minRows={7}
            required
          />
          {item.candidate_answer && (
            <Alert color="gray" title="Ответ кандидата">
              <Text style={{ whiteSpace: "pre-wrap" }}>
                {item.candidate_answer}
              </Text>
            </Alert>
          )}
          {isCreateNew && (
            <Stack gap="xs">
              <Group grow align="flex-end">
                <Select
                  label="Набор карточек"
                  value={deckId}
                  data={item.deck_options.map((option) => ({
                    value: option.id,
                    label: option.title,
                  }))}
                  onChange={changeDeck}
                  required
                  searchable
                />
                {createCategory ? (
                  <TextInput
                    label="Новая тема"
                    value={newCategory}
                    onChange={(event) =>
                      setNewCategory(event.currentTarget.value)
                    }
                    required
                  />
                ) : (
                  <Select
                    label="Существующая тема"
                    value={category}
                    data={selectedDeck?.categories ?? []}
                    onChange={setCategory}
                    disabled={!selectedDeck}
                    nothingFoundMessage="В этом наборе пока нет тем"
                    required
                    searchable
                  />
                )}
              </Group>
              <Button
                variant="subtle"
                size="compact-sm"
                w="fit-content"
                onClick={() => setCreateCategory((value) => !value)}
              >
                {createCategory
                  ? "Выбрать существующую тему"
                  : "Нужной темы нет — создать новую"}
              </Button>
            </Stack>
          )}
          {isCreateNew && (
            <Stack gap="xs">
              <Switch
                label="Указать частоту вручную"
                description="По умолчанию частота рассчитывается по подтверждённым появлениям вопроса."
                checked={frequencyMode === "manual"}
                onChange={(event) =>
                  setFrequencyMode(
                    event.currentTarget.checked ? "manual" : "automatic",
                  )
                }
              />
              {frequencyMode === "manual" && (
                <Select
                  label="Частота"
                  value={frequency}
                  data={[
                    { value: "frequent", label: "Частый вопрос" },
                    { value: "occasional", label: "Нечастый вопрос" },
                  ]}
                  onChange={(value) =>
                    setFrequency(
                      value === "frequent" ? "frequent" : "occasional",
                    )
                  }
                />
              )}
            </Stack>
          )}
          <Group>
            <Button
              loading={moderation.isPending}
              disabled={
                !question.trim() ||
                !answer.trim() ||
                (!targetCard && !isCreateNew) ||
                (isCreateNew && (!deckId || !moderationCategory?.trim()))
              }
              onClick={() => submit("approve")}
            >
              {targetCard
                ? "Связать с карточкой"
                : isCreateNew
                  ? "Создать карточку"
                  : "Выберите действие"}
            </Button>
            <Button
              color="gray"
              variant="light"
              loading={moderation.isPending}
              onClick={() => submit("reject")}
            >
              Отклонить
            </Button>
          </Group>
        </Stack>
      </Card>
    </Stack>
  );
}

export function AdminInterviewQuestionModerationEditPage() {
  const { questionId = "" } = useParams();
  const query = useAdminQuestionModerationDetail(questionId);
  if (query.isPending) return <LoadingState label="Загружаем вопрос…" />;
  if (query.isError)
    return (
      <ErrorState error={query.error} retry={() => void query.refetch()} />
    );
  return <ModerationForm key={query.data.question_id} item={query.data} />;
}
