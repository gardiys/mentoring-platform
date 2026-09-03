import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { InterviewIntelligencePage } from "../src/pages/InterviewIntelligencePage";
import type { IntelligenceInterviewDetail, User } from "../src/types/api";
import { renderPage } from "./render";

const interviewId = "70000000-0000-4000-8000-000000000001";

const student: User = {
  id: "20000000-0000-4000-8000-000000000001",
  telegram_id: 123456789,
  first_name: "Иван",
  last_name: null,
  email: null,
  role: "student",
  onboarding_completed_at: "2026-08-01T00:00:00Z",
  is_active: true,
};

const detail: IntelligenceInterviewDetail = {
  id: interviewId,
  stage_id: "71000000-0000-4000-8000-000000000001",
  process_id: "72000000-0000-4000-8000-000000000001",
  student_id: student.id,
  student_name: student.first_name,
  student_telegram_username: "ivan_backend",
  company_name: "Яндекс",
  position_name: "Python developer",
  track_id: "40000000-0000-4000-8000-000000000001",
  track_slug: "python",
  track_title: "Python",
  interview_type: "technical",
  interviewed_at: "2026-08-04T12:00:00Z",
  processing_status: "ready",
  failed_stage: null,
  processing_error_code: null,
  processing_error_message: null,
  can_requeue_processing: false,
  duration_ms: 1_800_000,
  question_count: 1,
  suggested_review_count: 0,
  reviewed_count: 1,
  reviewed_at: null,
  reviewed_by_user_id: null,
  created_at: "2026-08-05T09:00:00Z",
  updated_at: "2026-08-05T09:00:00Z",
  media_filename: "interview.mp4",
  media_content_type: "video/mp4",
  media_size: 10_000,
  speakers: [],
  transcript: [
    {
      id: "73000000-0000-4000-8000-000000000001",
      speaker_id: "74000000-0000-4000-8000-000000000001",
      speaker_key: "A",
      speaker_role: "candidate",
      sequence_number: 1,
      start_ms: 1_000,
      end_ms: 5_000,
      text: "Уникальная реплика из расшифровки",
    },
  ],
  questions: [
    {
      id: "75000000-0000-4000-8000-000000000001",
      sequence_number: 1,
      question_text: "Как работает GIL?",
      question_start_ms: 1_000,
      question_end_ms: 3_000,
      answer_start_ms: 3_000,
      answer_end_ms: 8_000,
      category: "Python",
      question_kind: "technical",
      subcategory: "Многопоточность",
      difficulty: "middle",
      confidence: 0.95,
      is_low_confidence: false,
      moderation_status: "approved",
      published_card_id: null,
      answer: {
        id: "76000000-0000-4000-8000-000000000001",
        answer_text: "GIL ограничивает параллельное исполнение байткода.",
        start_ms: 3_000,
        end_ms: 8_000,
        reviews: [
          {
            id: "77000000-0000-4000-8000-000000000001",
            parent_review_id: null,
            source: "ai",
            status: "approved",
            assessment: "mostly_correct",
            score: 0.8,
            summary: "Основная идея сформулирована верно.",
            strengths: [],
            problems: [],
            missing_points: ["Добавить пример CPU-bound задачи"],
            incorrect_statements: [],
            suggested_better_answer: null,
            model_name: "test-model",
            prompt_version: "test-prompt",
            created_by_user_id: null,
            rejection_reason: null,
            created_at: "2026-08-05T09:00:00Z",
          },
        ],
      },
    },
  ],
  mentor_comments: [],
  overview: {
    overall_summary: "Уникальный общий вывод по собеседованию.",
    technical_score: 0.8,
    technical_summary: "Уникальное техническое резюме.",
    technical_topics: [
      {
        topic: "Python: многопоточность",
        score: 0.8,
        summary: "Базовое понимание GIL есть.",
        strengths: ["Понимает назначение GIL"],
        gaps: ["Не хватило практического примера"],
        next_step: "Сравнить threading и multiprocessing.",
        evidence_question_numbers: [1],
        questions_count: 1,
        confidence: 0.9,
      },
    ],
    priority_actions: [
      {
        title: "Приоритетное действие 1",
        reason: "Причина 1",
        steps: ["Шаг 1"],
        success_criterion: "Критерий 1",
        related_topics: ["Python"],
      },
      {
        title: "Приоритетное действие 2",
        reason: "Причина 2",
        steps: ["Шаг 2"],
        success_criterion: "Критерий 2",
        related_topics: ["Python"],
      },
      {
        title: "Приоритетное действие 3",
        reason: "Причина 3",
        steps: ["Шаг 3"],
        success_criterion: "Критерий 3",
        related_topics: ["Python"],
      },
      {
        title: "Лишнее приоритетное действие 4",
        reason: "Этот элемент не должен попасть в интерфейс",
        steps: ["Лишний шаг"],
        success_criterion: "Лишний критерий",
        related_topics: ["Python"],
      },
    ],
    key_topics: ["Python", "GIL"],
    communication_summary: "Уникальное резюме коммуникации.",
    communication_score: 0.7,
    communication_dimensions: [],
    communication_strengths: ["Отвечает последовательно"],
    communication_growth_areas: ["Сократить вводную часть"],
    caveats: [],
    model_name: "test-model",
    prompt_version: "test-prompt",
  },
  processing: {
    status: "ready",
    failed_stage: null,
    error_code: null,
    error_message: null,
    transcribed: true,
    candidate_selected: true,
    questions_found: 1,
    reviews_completed: 1,
    attempts: [],
  },
};

afterEach(() => vi.restoreAllMocks());

function expectBefore(first: HTMLElement, second: HTMLElement) {
  expect(
    first.compareDocumentPosition(second) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
}

it("показывает компактный AI-отчёт до soft skills и материалов", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "intelligenceInterview").mockResolvedValue(detail);

  renderPage(
    <InterviewIntelligencePage />,
    `/interviews/analysis/${interviewId}`,
    "/interviews/analysis/:interviewId",
  );

  const verdict = await screen.findByText("Вердикт");
  const actions = screen.getByText("Приоритетные улучшения");
  const technical = screen.getByText("Техническая оценка по темам");
  const communication = screen.getByText("Коммуникация и подача");
  const questions = screen.getByText("Вопросы и ответы");
  const materials = screen.getByText("Запись и расшифровка");

  expectBefore(verdict, actions);
  expectBefore(actions, technical);
  expectBefore(technical, communication);
  expectBefore(communication, questions);
  expectBefore(questions, materials);

  expect(screen.getByText("Приоритетное действие 1")).toBeVisible();
  expect(screen.getByText("Приоритетное действие 2")).toBeVisible();
  expect(screen.getByText("Приоритетное действие 3")).toBeVisible();
  expect(
    screen.queryByText("Лишнее приоритетное действие 4"),
  ).not.toBeInTheDocument();

  await userEvent.click(
    screen.getByRole("button", { name: /Python: многопоточность/i }),
  );
  const evidenceLink = await screen.findByRole("link", {
    name: "Открыть вопрос №1",
  });
  expect(evidenceLink).toHaveAttribute(
    "href",
    "#question-75000000-0000-4000-8000-000000000001",
  );
  await userEvent.click(evidenceLink);
  await waitFor(() =>
    expect(screen.getByText("Как работает GIL?")).toBeVisible(),
  );

  const communicationSummary = screen.getByText(
    "Уникальное резюме коммуникации.",
  );
  expect(communicationSummary).not.toBeVisible();

  await userEvent.click(
    screen.getByRole("button", { name: /Коммуникация и подача/i }),
  );
  await waitFor(() => expect(communicationSummary).toBeVisible());
});
