import { screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { CommunicationProgress } from "../src/components/CommunicationProgress";
import { useCoachingHistory } from "../src/features/interviews/coaching";
import { renderPage } from "./render";

vi.mock("../src/features/auth/queries", () => ({
  useMe: () => ({ data: { id: "student" } }),
}));
vi.mock("../src/features/interviews/coaching", () => ({
  useCoachingHistory: vi.fn(),
  useCoachingAction: () => ({ isPending: false, mutate: vi.fn() }),
}));

beforeEach(() => {
  vi.mocked(useCoachingHistory, { partial: true }).mockReturnValue({
    isPending: false,
    isError: false,
    data: {
      interview_count: 3,
      limit: 30,
      truncated: true,
      observations: [
        {
          interview_id: "rejected",
          analysis_revision: 1,
          date: "2026-09-03",
          interview_type: "hr",
          completed_at: null,
          decision: "rejected",
          skill: "structure",
          name: "Структура ответа",
          score: 0.1,
          confidence: 0.9,
          summary: "Отклонённый вывод",
          evidence_utterance_ids: [],
          exercise: {
            task: "Отклонённое упражнение",
            success_criterion: "Не показывать",
          },
        },
        {
          interview_id: "approved",
          analysis_revision: 2,
          date: "2026-09-02",
          interview_type: "hr",
          completed_at: null,
          decision: "approved",
          skill: "structure",
          name: "Структура ответа",
          score: 0.85,
          example_score: 0.4,
          observation_count: 10,
          confidence: 0.9,
          summary: "Есть слабый пример",
          evidence_utterance_ids: [],
          exercise: {
            task: "Упражнение по слабому примеру",
            success_criterion: "Назван результат",
          },
        },
        {
          interview_id: "earlier",
          analysis_revision: 1,
          date: "2026-09-01",
          interview_type: "hr",
          completed_at: null,
          skill: "structure",
          name: "Структура ответа",
          score: 0.3,
          confidence: 0.8,
          summary: "Ранний пример",
          evidence_utterance_ids: [],
        },
      ],
    },
  });
});

it("keeps rejected decisions visible but excludes them from practice and comparisons", () => {
  renderPage(<CommunicationProgress practice />);
  expect(screen.getByText(/вывод отклонён ментором/)).toBeVisible();
  expect(screen.queryByText("Отклонённое упражнение")).not.toBeInTheDocument();
  expect(screen.getByText("Упражнение по слабому примеру")).toBeVisible();
  expect(screen.getByText("Выполнено 0 из 1")).toBeVisible();
  expect(screen.queryByText(/п\.п\./)).not.toBeInTheDocument();
  expect(screen.queryByText(/Три разбора подряд/)).not.toBeInTheDocument();
  expect(screen.getByText(/после пересчёта разбора новый набор/)).toBeVisible();
  expect(screen.getByText(/Более ранние примеры доступны/)).toBeVisible();
  expect(screen.getByRole("link", { name: /85%.*ответов: 10/ })).toBeVisible();
});
