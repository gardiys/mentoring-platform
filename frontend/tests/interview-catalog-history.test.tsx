import { screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { InterviewCatalogHistoryPage } from "../src/pages/InterviewCatalogHistoryPage";
import type { InterviewCatalogHistoryPage as HistoryPage } from "../src/types/api";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

const history: HistoryPage = {
  items: [
    {
      stage_id: "71000000-0000-4000-8000-000000000001",
      process_id: "70000000-0000-4000-8000-000000000001",
      company_id: "73000000-0000-4000-8000-000000000001",
      company_name: "Яндекс",
      track_title: "Python",
      stage_type: "technical_interview",
      scheduled_at: "2026-08-10T12:00:00Z",
      description: "Алгоритмы, Python и проектирование API",
      first_viewed_at: "2026-08-11T09:00:00Z",
      last_viewed_at: "2026-08-13T09:00:00Z",
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
};

it("показывает историю просмотренных этапов", async () => {
  vi.spyOn(api, "interviewCatalogHistory").mockResolvedValue(history);
  renderPage(
    <InterviewCatalogHistoryPage />,
    "/interviews/catalog/history",
    "/interviews/catalog/history",
  );

  expect(await screen.findByText("Яндекс")).toBeInTheDocument();
  expect(screen.getByText(/Python · этап от/)).toBeInTheDocument();
  expect(
    screen.getByText(/Просмотрено 13 августа 2026/),
  ).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Открыть" })).toHaveAttribute(
    "href",
    "/interviews/catalog/73000000-0000-4000-8000-000000000001?stage=71000000-0000-4000-8000-000000000001",
  );
});

it("показывает пустое состояние без истории", async () => {
  vi.spyOn(api, "interviewCatalogHistory").mockResolvedValue({
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
  });
  renderPage(
    <InterviewCatalogHistoryPage />,
    "/interviews/catalog/history",
    "/interviews/catalog/history",
  );

  expect(
    await screen.findByText("Вы пока ничего не смотрели"),
  ).toBeInTheDocument();
});
