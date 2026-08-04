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
  matched_card_asked_count: 7,
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

it("предупреждает, когда вопрос уже существует", async () => {
  vi.spyOn(api, "adminQuestionModerationDetail").mockResolvedValue(question);

  renderPage(
    <AdminInterviewQuestionModerationEditPage />,
    `/admin/interview-question-moderation/${question.question_id}`,
    "/admin/interview-question-moderation/:questionId",
  );

  expect(
    await screen.findByText("Найдена существующая карточка"),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Уже зафиксировано появлений: 7/),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Учесть ещё одно появление" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Набор карточек")).toHaveValue("Backend");
  expect(screen.getByLabelText("Набор карточек")).toBeDisabled();
  expect(screen.getByLabelText("Тема")).toHaveValue("Python");
  expect(screen.getByLabelText("Тема")).toBeDisabled();
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
    matched_card_asked_count: null,
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
    matched_card_asked_count: null,
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
      }),
    ),
  );
});
