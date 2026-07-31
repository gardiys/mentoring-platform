import { screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { RoadmapsPage } from "../src/pages/RoadmapsPage";
import type { RoadmapListItem } from "../src/types/api";
import { renderPage } from "./render";

const roadmap: RoadmapListItem = {
  id: "roadmap-1",
  slug: "python-backend",
  title: "Python Backend",
  description: "Описание",
  completed_topics: 1,
  total_topics: 2,
  progress_percent: 50,
  started_at: null,
  completed_at: null,
  total_duration_days: 138,
  planned_completion_at: null,
};

describe("RoadmapsPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("показывает загрузку", () => {
    vi.spyOn(api, "roadmaps").mockReturnValue(new Promise(() => undefined));
    renderPage(<RoadmapsPage />);
    expect(screen.getByText("Загружаем роадмапы…")).toBeInTheDocument();
  });

  it("показывает данные", async () => {
    vi.spyOn(api, "roadmaps").mockResolvedValue([roadmap]);
    renderPage(<RoadmapsPage />);
    expect(await screen.findByText("Python Backend")).toBeInTheDocument();
    expect(screen.getByText("1 из 2 тем")).toBeInTheDocument();
  });

  it("показывает ошибку API", async () => {
    vi.spyOn(api, "roadmaps").mockRejectedValue(new Error("network"));
    renderPage(<RoadmapsPage />);
    expect(
      await screen.findByText("Не удалось загрузить данные"),
    ).toBeInTheDocument();
  });
});
