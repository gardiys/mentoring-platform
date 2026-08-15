import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { RoadmapPage } from "../src/pages/RoadmapPage";
import type { RoadmapDetail } from "../src/types/api";
import { renderPage } from "./render";

const detail: RoadmapDetail = {
  id: "r1",
  slug: "python-backend",
  title: "Python Backend",
  description: null,
  completed_topics: 0,
  total_topics: 1,
  progress_percent: 0,
  started_at: null,
  completed_at: null,
  total_duration_days: 2,
  planned_completion_at: null,
  sections: [
    {
      id: "s1",
      title: "Основы Python",
      description: null,
      duration_days: 2,
      deadline_at: null,
      topics: [
        {
          id: "t1",
          slug: "types",
          title: "Типы данных",
          description: null,
          estimated_minutes: 10,
          status: "not_started",
          first_completed_at: null,
          last_completed_at: null,
        },
      ],
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

it("RoadmapPage отображает разделы и темы", async () => {
  vi.spyOn(api, "roadmap").mockResolvedValue(detail);
  renderPage(
    <RoadmapPage />,
    "/roadmaps/python-backend",
    "/roadmaps/:roadmapSlug",
  );
  expect(await screen.findByText("Основы Python")).toBeInTheDocument();
  expect(screen.getByText("Типы данных")).toBeInTheDocument();
  expect(screen.getByText("План обучения — 2 дня")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Начать прохождение" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText(/Дата начала прохождения/)).toBeInTheDocument();
});

it("запускает роадмап и показывает рассчитанные дедлайны", async () => {
  vi.spyOn(api, "roadmap").mockResolvedValue(detail);
  const start = vi.spyOn(api, "startRoadmap").mockResolvedValue({
    ...detail,
    started_at: "2030-01-01T12:00:00Z",
    planned_completion_at: "2030-01-03T12:00:00Z",
    sections: [
      {
        ...detail.sections[0]!,
        deadline_at: "2030-01-03T12:00:00Z",
      },
    ],
  });
  renderPage(
    <RoadmapPage />,
    "/roadmaps/python-backend",
    "/roadmaps/:roadmapSlug",
  );

  const startedOn = await screen.findByLabelText(/Дата начала прохождения/);
  await userEvent.clear(startedOn);
  await userEvent.type(startedOn, "2030-01-01");

  await userEvent.click(
    await screen.findByRole("button", { name: "Начать прохождение" }),
  );

  expect(start).toHaveBeenCalledWith("python-backend", "2030-01-01");
  expect(
    await screen.findByText(/Плановое завершение — 3 января 2030/),
  ).toBeInTheDocument();
  expect(screen.getByText(/до 3 января 2030/)).toBeInTheDocument();
});

it("быстро фильтрует темы и раскрывает найденный раздел", async () => {
  vi.spyOn(api, "roadmap").mockResolvedValue({
    ...detail,
    total_topics: 2,
    sections: [
      ...detail.sections,
      {
        id: "s2",
        title: "Базы данных",
        description: "Хранение и обработка данных",
        duration_days: 3,
        deadline_at: null,
        topics: [
          {
            id: "t2",
            slug: "postgresql-indexes",
            title: "Индексы PostgreSQL",
            description: "B-tree и планы запросов",
            estimated_minutes: 20,
            status: "completed",
            first_completed_at: "2026-08-01T10:00:00Z",
            last_completed_at: "2026-08-01T10:00:00Z",
          },
        ],
      },
    ],
  });
  renderPage(
    <RoadmapPage />,
    "/roadmaps/python-backend",
    "/roadmaps/:roadmapSlug",
  );

  const search = await screen.findByRole("textbox", {
    name: "Поиск по темам",
  });
  await userEvent.type(search, "postgresql");

  expect(screen.getByText("Индексы PostgreSQL")).toBeVisible();
  expect(screen.queryByText("Типы данных")).not.toBeInTheDocument();
  expect(screen.getByText("Найдено тем: 1")).toBeVisible();

  await userEvent.clear(search);
  await userEvent.type(search, "несуществующая тема");
  expect(screen.getByText("Темы не найдены")).toBeVisible();
});
