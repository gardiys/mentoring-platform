import {
  Alert,
  Badge,
  Button,
  Card,
  Group,
  Select,
  Stack,
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
import type { AdminQuestionModerationDetail } from "../types/api";

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

function ModerationForm({ item }: { item: AdminQuestionModerationDetail }) {
  const navigate = useNavigate();
  const moderation = useIntelligenceQuestionModeration();
  const initialDeckId =
    item.matched_card_deck_id ?? item.deck_options[0]?.id ?? null;
  const initialDeck = item.deck_options.find(
    (option) => option.id === initialDeckId,
  );
  const initialCategory =
    item.matched_card_category ??
    matchingCategory(initialDeck?.categories ?? [], item.category);
  const [question, setQuestion] = useState(item.question_text);
  const [answer, setAnswer] = useState(
    item.suggested_answer || item.candidate_answer || "",
  );
  const [deckId, setDeckId] = useState<string | null>(initialDeckId);
  const [category, setCategory] = useState<string | null>(initialCategory);
  const [createCategory, setCreateCategory] = useState(false);
  const [newCategory, setNewCategory] = useState(item.category);
  const [frequency, setFrequency] = useState<"frequent" | "occasional">(
    "occasional",
  );
  const selectedDeck = item.deck_options.find((option) => option.id === deckId);
  const matchedDeck = item.deck_options.find(
    (option) => option.id === item.matched_card_deck_id,
  );
  const moderationDeckId = item.matched_card_id
    ? item.matched_card_deck_id
    : deckId;
  const moderationCategory = item.matched_card_id
    ? item.matched_card_category
    : createCategory
      ? newCategory.trim()
      : category;
  const allowNavigation = useUnsavedChanges(
    question !== item.question_text ||
      answer !== (item.suggested_answer || item.candidate_answer || "") ||
      deckId !== initialDeckId ||
      category !== initialCategory ||
      createCategory ||
      frequency !== "occasional",
  );

  const changeDeck = (value: string | null) => {
    const nextDeck = item.deck_options.find((option) => option.id === value);
    setDeckId(value);
    setCategory(matchingCategory(nextDeck?.categories ?? [], item.category));
    setCreateCategory(false);
  };

  const submit = (action: "approve" | "reject") => {
    if (
      action === "reject" &&
      !window.confirm(
        "Отклонить вопрос? Он не будет добавлен в общую базу карточек.",
      )
    )
      return;
    moderation.mutate(
      {
        interviewId: item.interview_id,
        questionId: item.question_id,
        payload:
          action === "approve"
            ? {
                action,
                question_markdown: question.trim(),
                answer_markdown: answer.trim(),
                deck_id: moderationDeckId ?? undefined,
                category: moderationCategory?.trim(),
                create_category: !item.matched_card_id && createCategory,
                frequency,
              }
            : { action },
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
      {item.matched_card_id && (
        <Alert color="blue" title="Найдена существующая карточка">
          <Stack gap="xs">
            <Text>{item.matched_card_question}</Text>
            <Text size="sm">
              Уже зафиксировано появлений: {item.matched_card_asked_count}.
              После подтверждения новая карточка не создастся — добавится
              компания и увеличится счётчик.
            </Text>
            <Text size="sm">
              Набор: {matchedDeck?.title ?? "—"} · Тема:{" "}
              {item.matched_card_category ?? "—"}
            </Text>
          </Stack>
        </Alert>
      )}
      {!item.matched_card_id && item.deck_options.length === 0 && (
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
          />
          <Textarea
            label="Проверенный ответ для обратной стороны карточки"
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
          {item.matched_card_id ? (
            <Group grow align="flex-end">
              <TextInput
                label="Набор карточек"
                value={matchedDeck?.title ?? ""}
                disabled
              />
              <TextInput
                label="Тема"
                value={item.matched_card_category ?? ""}
                disabled
              />
            </Group>
          ) : (
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
          <Group grow align="flex-end">
            <Select
              label="Частота"
              value={frequency}
              data={[
                { value: "frequent", label: "Частый вопрос" },
                { value: "occasional", label: "Нечастый вопрос" },
              ]}
              onChange={(value) =>
                setFrequency(value === "frequent" ? "frequent" : "occasional")
              }
            />
          </Group>
          <Group>
            <Button
              loading={moderation.isPending}
              disabled={
                !question.trim() ||
                !answer.trim() ||
                !moderationDeckId ||
                !moderationCategory?.trim()
              }
              onClick={() => submit("approve")}
            >
              {item.matched_card_id
                ? "Учесть ещё одно появление"
                : "Создать карточку"}
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
