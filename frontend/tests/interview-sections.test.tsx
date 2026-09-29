import { screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import {
  InterviewsPage,
  InterviewAnalysesPage,
  InterviewJournalPage,
  InterviewMocksPage,
  InterviewMaterialsPage,
} from "../src/pages/InterviewsPage";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

it.each([
  [
    InterviewsPage,
    "interviewDecks",
    "Вопросы с собеседований",
    "Для твоих учебных треков пока нет опубликованных колод.",
  ],
  [
    InterviewAnalysesPage,
    "intelligenceInterviews",
    "AI-разборы собеседований",
    "Разборов пока нет",
  ],
  [
    InterviewJournalPage,
    "interviewProcesses",
    "Дневник собеседований",
    "Активных процессов пока нет",
  ],
  [
    InterviewMocksPage,
    "myMockInterviews",
    "Мок-собеседования",
    "Мок-собеседования пока не назначены",
  ],
  [
    InterviewMaterialsPage,
    "myMentorDocuments",
    "Резюме и легенда",
    "Материалы пока не добавлены",
  ],
] as const)(
  "раздел %s загружает только свои данные",
  async (Page, method, title, empty) => {
    const requests = {
      interviewDecks: vi.spyOn(api, "interviewDecks").mockResolvedValue([]),
      intelligenceInterviews: vi
        .spyOn(api, "intelligenceInterviews")
        .mockResolvedValue({ items: [], total: 0, limit: 6, offset: 0 }),
      interviewProcesses: vi
        .spyOn(api, "interviewProcesses")
        .mockResolvedValue([]),
      myMockInterviews: vi.spyOn(api, "myMockInterviews").mockResolvedValue([]),
      myMentorDocuments: vi
        .spyOn(api, "myMentorDocuments")
        .mockResolvedValue([]),
    };
    renderPage(<Page />);
    expect(
      screen.getByRole("heading", { level: 1, name: title }),
    ).toBeInTheDocument();
    expect(await screen.findByText(empty)).toBeInTheDocument();
    for (const [key, request] of Object.entries(requests)) {
      expect(request).toHaveBeenCalledTimes(key === method ? 1 : 0);
    }
  },
);
