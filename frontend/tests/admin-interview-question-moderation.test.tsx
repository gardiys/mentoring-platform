import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminInterviewQuestionModerationEditPage } from "../src/pages/AdminInterviewQuestionModerationEditPage";
import { AdminInterviewQuestionModerationPage } from "../src/pages/AdminInterviewQuestionModerationPage";
import type { AdminQuestionModerationDetail } from "../src/types/api";
import { renderPage } from "./render";

const deckId = "50000000-0000-4000-8000-000000000001";

const question: AdminQuestionModerationDetail = {
  question_id: "10000000-0000-4000-8000-000000000001",
  interview_id: "20000000-0000-4000-8000-000000000001",
  question_text: "Как работает GIL в Python?",
  category: "Python",
  question_kind: "technical",
  difficulty: "middle",
  moderation_status: "mentor_approved",
  company_name: "Яндекс",
  track_id: "30000000-0000-4000-8000-000000000001",
  track_slug: "python",
  track_title: "Python",
  student_name: "Иван Иванов",
  interviewed_at: "2026-08-02T10:00:00Z",
  candidate_answer: "GIL ограничивает параллельное выполнение байткода.",
  suggested_answer: "GIL — это мьютекс интерпретатора CPython.",
  matched_card_id: "40000000-0000-4000-8000-000000000001",
  matched_card_deck_id: deckId,
  matched_card_category: "Python",
  matched_card_question: "## Как работает GIL в Python?",
  matched_card_answer:
    "GIL не позволяет потокам одновременно исполнять Python-байткод.",
  matched_card_asked_count: 7,
  card_candidates: [
    {
      id: "40000000-0000-4000-8000-000000000001",
      deck_id: deckId,
      deck_title: "Backend",
      category: "Python",
      question_markdown: "## Как работает GIL в Python?",
      answer_markdown:
        "GIL не позволяет потокам одновременно исполнять Python-байткод.",
      matched_text: "## Как работает GIL в Python?",
      asked_count: 7,
      frequency: "frequent",
      similarity: 1,
      match_type: "exact",
      matched_source: "card",
    },
  ],
  deck_options: [
    {
      id: deckId,
      title: "Backend",
      categories: ["Django", "Python"],
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

it("показывает отдельную таблицу вопросов для карточек", async () => {
  vi.spyOn(api, "adminQuestionModeration").mockResolvedValue({
    items: [question],
    total: 1,
    limit: 20,
    offset: 0,
  });

  renderPage(<AdminInterviewQuestionModerationPage />);

  expect(await screen.findByText(question.question_text)).toBeInTheDocument();
  expect(screen.getByText("Рекомендован ментором")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Открыть" })).toHaveAttribute(
    "href",
    `/admin/interview-question-moderation/${question.question_id}`,
  );
});

it("автоматически выбирает только точное совпадение с основной карточкой", async () => {
  vi.spyOn(api, "adminQuestionModerationDetail").mockResolvedValue(question);

  renderPage(
    <AdminInterviewQuestionModerationEditPage />,
    `/admin/interview-question-moderation/${question.question_id}`,
    "/admin/interview-question-moderation/:questionId",
  );

  expect(
    await screen.findByText("Найдена существующая карточка"),
  ).toBeInTheDocument();
  expect(screen.getByText("Спросили раз: 7")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Связать с карточкой" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("radio", {
      name: "Связать с карточкой: Как работает GIL в Python?",
    }),
  ).toBeChecked();
  expect(screen.getByDisplayValue(question.question_text)).toBeEnabled();
  expect(
    screen.queryByRole("radio", {
      name: "Создать новую карточку, это другой вопрос",
    }),
  ).not.toBeInTheDocument();
  expect(
    screen.getByRole("textbox", { name: "Ответ связанной карточки" }),
  ).toHaveValue(question.matched_card_answer);
  expect(
    screen.getAllByText(question.matched_card_answer ?? ""),
  ).not.toHaveLength(0);
  expect(screen.queryByLabelText("Набор карточек")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Существующая тема")).not.toBeInTheDocument();
});

it("требует явного подтверждения точного совпадения с алиасом", async () => {
  const candidate = {
    ...question.card_candidates[0]!,
    matched_source: "approved_alias" as const,
    matched_text: "Объясни принцип работы GIL",
  };
  const aliasQuestion: AdminQuestionModerationDetail = {
    ...question,
    matched_card_id: null,
    matched_card_deck_id: null,
    matched_card_category: null,
    matched_card_question: null,
    matched_card_answer: null,
    matched_card_asked_count: null,
    card_candidates: [candidate],
  };
  vi.spyOn(api, "adminQuestionModerationDetail").mockResolvedValue(
    aliasQuestion,
  );

  renderPage(
    <AdminInterviewQuestionModerationEditPage />,
    `/admin/interview-question-moderation/${aliasQuestion.question_id}`,
    "/admin/interview-question-moderation/:questionId",
  );

  expect(
    await screen.findByText("Точно совпало с подтверждённым вариантом"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Совпавшая формулировка: «Объясни принцип работы GIL»"),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("radio", {
      name: "Связать с карточкой: Как работает GIL в Python?",
    }),
  ).not.toBeChecked();
  expect(
    screen.getByRole("button", { name: "Выберите действие" }),
  ).toBeDisabled();
});

it("связывает похожий вопрос только после явного подтверждения", async () => {
  const user = userEvent.setup();
  const candidateId = "40000000-0000-4000-8000-000000000099";
  const similarQuestion: AdminQuestionModerationDetail = {
    ...question,
    question_id: "10000000-0000-4000-8000-000000000099",
    question_text:
      "Чем ты пользовался Kafka или RabbitMQ? Знаешь, в чём разница?",
    matched_card_id: null,
    matched_card_deck_id: null,
    matched_card_category: null,
    matched_card_question: null,
    matched_card_answer: null,
    matched_card_asked_count: null,
    card_candidates: [
      {
        id: candidateId,
        deck_id: deckId,
        deck_title: "Backend",
        category: "Брокеры сообщений",
        question_markdown: "## Расскажи, в чём отличия Kafka и RabbitMQ?",
        answer_markdown:
          "Kafka — распределённый журнал, RabbitMQ — брокер очередей.",
        matched_text: "Kafka и RabbitMQ — в чём разница?",
        asked_count: 12,
        frequency: "frequent",
        similarity: 0.87,
        match_type: "similar",
        matched_source: "approved_alias",
      },
    ],
  };
  vi.spyOn(api, "adminQuestionModerationDetail").mockResolvedValue(
    similarQuestion,
  );
  const moderate = vi
    .spyOn(api, "moderateIntelligenceQuestion")
    .mockReturnValue(new Promise(() => undefined));

  renderPage(
    <AdminInterviewQuestionModerationEditPage />,
    `/admin/interview-question-moderation/${similarQuestion.question_id}`,
    "/admin/interview-question-moderation/:questionId",
  );

  expect(await screen.findByText("Возможные совпадения")).toBeInTheDocument();
  expect(screen.getByText("Похожий вопрос · 87%")).toBeInTheDocument();
  expect(screen.getByText("Спросили раз: 12")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Выберите действие" }),
  ).toBeDisabled();

  const correctedQuestion = "Чем отличаются Kafka и RabbitMQ?";
  const questionInput = screen.getByRole("textbox", { name: /Вопрос/ });
  const answerInput = screen.getByRole("textbox", {
    name: /Проверенный ответ для обратной стороны карточки/,
  });
  await user.clear(questionInput);
  await user.type(questionInput, correctedQuestion);
  await user.clear(answerInput);
  await user.type(answerInput, "Этот ответ не должен попасть в карточку");

  await user.click(
    screen.getByRole("radio", {
      name: "Связать с карточкой: Расскажи, в чём отличия Kafka и RabbitMQ?",
    }),
  );
  expect(screen.getByRole("textbox", { name: /Вопрос/ })).toHaveValue(
    correctedQuestion,
  );
  const linkedAnswerInput = screen.getByRole("textbox", {
    name: "Ответ связанной карточки",
  });
  expect(linkedAnswerInput).toHaveValue(
    "Kafka — распределённый журнал, RabbitMQ — брокер очередей.",
  );
  await user.clear(linkedAnswerInput);
  await user.type(linkedAnswerInput, "Обновлённый проверенный ответ");
  await user.click(screen.getByRole("button", { name: "Связать с карточкой" }));

  await waitFor(() =>
    expect(moderate).toHaveBeenCalledWith(
      similarQuestion.interview_id,
      similarQuestion.question_id,
      {
        action: "approve",
        target_card_id: candidateId,
        question_markdown: correctedQuestion,
        answer_markdown: "Обновлённый проверенный ответ",
      },
    ),
  );
});

it("позволяет явно создать новую карточку вместо похожей", async () => {
  const user = userEvent.setup();
  const similarQuestion: AdminQuestionModerationDetail = {
    ...question,
    question_id: "10000000-0000-4000-8000-000000000098",
    question_text: "Когда стоит применять очередь сообщений?",
    matched_card_id: null,
    matched_card_deck_id: null,
    matched_card_category: null,
    matched_card_question: null,
    matched_card_answer: null,
    matched_card_asked_count: null,
    card_candidates: [
      {
        id: "40000000-0000-4000-8000-000000000098",
        deck_id: deckId,
        deck_title: "Backend",
        category: "Python",
        question_markdown: "## Какие гарантии доставки есть у RabbitMQ?",
        answer_markdown: "At most once, at least once и exactly once.",
        matched_text: "Какие гарантии доставки есть у RabbitMQ?",
        asked_count: 2,
        frequency: "occasional",
        similarity: 0.68,
        match_type: "similar",
        matched_source: "card",
      },
    ],
  };
  vi.spyOn(api, "adminQuestionModerationDetail").mockResolvedValue(
    similarQuestion,
  );
  const moderate = vi
    .spyOn(api, "moderateIntelligenceQuestion")
    .mockReturnValue(new Promise(() => undefined));

  renderPage(
    <AdminInterviewQuestionModerationEditPage />,
    `/admin/interview-question-moderation/${similarQuestion.question_id}`,
    "/admin/interview-question-moderation/:questionId",
  );

  await user.click(
    await screen.findByRole("radio", {
      name: "Создать новую карточку, это другой вопрос",
    }),
  );
  expect(await screen.findByDisplayValue("Backend")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Создать карточку" }));

  await waitFor(() =>
    expect(moderate).toHaveBeenCalledWith(
      similarQuestion.interview_id,
      similarQuestion.question_id,
      expect.objectContaining({
        action: "approve",
        create_new_card: true,
        frequency_mode: "automatic",
        deck_id: deckId,
        category: "Python",
      }),
    ),
  );
  expect(moderate.mock.calls[0]?.[2]).not.toHaveProperty("target_card_id");
  expect(moderate.mock.calls[0]?.[2]).not.toHaveProperty("frequency");
});

it("публикует новый вопрос в выбранную существующую тему", async () => {
  const user = userEvent.setup();
  const newQuestion: AdminQuestionModerationDetail = {
    ...question,
    question_id: "10000000-0000-4000-8000-000000000002",
    question_text: "Чем процесс отличается от потока?",
    category: "python",
    matched_card_id: null,
    matched_card_deck_id: null,
    matched_card_category: null,
    matched_card_question: null,
    matched_card_answer: null,
    matched_card_asked_count: null,
    card_candidates: [],
  };
  vi.spyOn(api, "adminQuestionModerationDetail").mockResolvedValue(newQuestion);
  const moderate = vi
    .spyOn(api, "moderateIntelligenceQuestion")
    .mockReturnValue(new Promise(() => undefined));

  renderPage(
    <AdminInterviewQuestionModerationEditPage />,
    `/admin/interview-question-moderation/${newQuestion.question_id}`,
    "/admin/interview-question-moderation/:questionId",
  );

  expect(await screen.findByDisplayValue("Backend")).toBeInTheDocument();
  expect(screen.getAllByDisplayValue("Python")[0]).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Создать карточку" }));

  await waitFor(() =>
    expect(moderate).toHaveBeenCalledWith(
      newQuestion.interview_id,
      newQuestion.question_id,
      expect.objectContaining({
        action: "approve",
        deck_id: deckId,
        category: "Python",
        create_category: false,
        create_new_card: true,
        frequency_mode: "automatic",
      }),
    ),
  );
});

it("создаёт новую тему только после явного выбора", async () => {
  const user = userEvent.setup();
  const newQuestion: AdminQuestionModerationDetail = {
    ...question,
    question_id: "10000000-0000-4000-8000-000000000003",
    question_text: "Что такое event loop?",
    category: "Concurrency",
    matched_card_id: null,
    matched_card_deck_id: null,
    matched_card_category: null,
    matched_card_question: null,
    matched_card_answer: null,
    matched_card_asked_count: null,
    card_candidates: [],
  };
  vi.spyOn(api, "adminQuestionModerationDetail").mockResolvedValue(newQuestion);
  const moderate = vi
    .spyOn(api, "moderateIntelligenceQuestion")
    .mockReturnValue(new Promise(() => undefined));

  renderPage(
    <AdminInterviewQuestionModerationEditPage />,
    `/admin/interview-question-moderation/${newQuestion.question_id}`,
    "/admin/interview-question-moderation/:questionId",
  );

  const approve = await screen.findByRole("button", {
    name: "Создать карточку",
  });
  expect(approve).toBeDisabled();
  await user.click(
    screen.getByRole("button", { name: "Нужной темы нет — создать новую" }),
  );
  expect(screen.getByDisplayValue("Concurrency")).toBeInTheDocument();
  expect(approve).toBeEnabled();
  await user.click(approve);

  await waitFor(() =>
    expect(moderate).toHaveBeenCalledWith(
      newQuestion.interview_id,
      newQuestion.question_id,
      expect.objectContaining({
        action: "approve",
        deck_id: deckId,
        category: "Concurrency",
        create_category: true,
        create_new_card: true,
        frequency_mode: "automatic",
      }),
    ),
  );
});
