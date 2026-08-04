import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminRoadmapCreatePage } from "../src/pages/AdminRoadmapCreatePage";
import { AdminRoadmapEditPage } from "../src/pages/AdminRoadmapEditPage";
import { AdminRoadmapsPage } from "../src/pages/AdminRoadmapsPage";
import type {
  AdminRoadmapOutline,
  AdminRoadmapRead,
  AdminRoadmapSummary,
} from "../src/types/api";
import { renderPage } from "./render";

const created: AdminRoadmapRead = {
  id: "roadmap-id",
  slug: "django-backend",
  title: "Django Backend",
  description: null,
  position: 0,
  is_published: false,
  sections: [
    {
      id: "section-id",
      title: "Django",
      description: null,
      position: 0,
      duration_days: null,
      topics: [
        {
          id: "topic-id",
          slug: "django-orm",
          title: "Django ORM",
          description: null,
          content_markdown: "# Django ORM",
          position: 0,
          estimated_minutes: null,
          is_published: false,
          media: [],
        },
      ],
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

const summary: AdminRoadmapSummary = {
  id: created.id,
  slug: created.slug,
  title: created.title,
  description: created.description,
  position: created.position,
  is_published: created.is_published,
  section_count: 1,
  topic_count: 1,
};

const outline: AdminRoadmapOutline = {
  ...summary,
  sections: created.sections.map((section) => ({
    id: section.id,
    title: section.title,
    description: section.description,
    position: section.position,
    duration_days: section.duration_days,
    topics: section.topics.map((topic) => ({
      id: topic.id,
      slug: topic.slug,
      title: topic.title,
      position: topic.position,
      estimated_minutes: topic.estimated_minutes,
      is_published: topic.is_published,
    })),
  })),
};

it("AdminRoadmapsPage показывает черновики", async () => {
  vi.spyOn(api, "adminRoadmapSummaries").mockResolvedValue([summary]);
  renderPage(<AdminRoadmapsPage />);

  expect(await screen.findByText("Django Backend")).toBeInTheDocument();
  expect(screen.getByText("Черновик")).toBeInTheDocument();
});

it("конструктор отправляет вложенный roadmap", async () => {
  const create = vi
    .spyOn(api, "createAdminRoadmap")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <AdminRoadmapCreatePage />,
    "/admin/roadmaps/new",
    "/admin/roadmaps/new",
  );

  await userEvent.type(
    screen.getByLabelText(/^Название роадмапа/),
    "Django Backend",
  );
  await userEvent.type(
    screen.getByLabelText(/^Slug роадмапа/),
    "django-backend",
  );
  await userEvent.type(screen.getByLabelText(/^Название раздела/), "Django");
  await userEvent.type(screen.getByLabelText(/^Название темы/), "Django ORM");
  await userEvent.type(screen.getByLabelText(/^Slug темы/), "django-orm");
  await userEvent.click(
    screen.getByRole("button", { name: "Создать роадмап" }),
  );

  expect(create).toHaveBeenCalledWith(
    expect.objectContaining({
      slug: "django-backend",
      sections: [
        expect.objectContaining({
          title: "Django",
          topics: [
            expect.objectContaining({
              slug: "django-orm",
              title: "Django ORM",
            }),
          ],
        }),
      ],
    }),
  );
});

it("редактор сохраняет настройки без отправки всех тем", async () => {
  vi.spyOn(api, "adminRoadmapOutline").mockResolvedValue(outline);
  const update = vi
    .spyOn(api, "updateAdminRoadmapSettings")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <AdminRoadmapEditPage />,
    "/admin/roadmaps/roadmap-id/edit",
    "/admin/roadmaps/:roadmapId/edit",
  );

  const title = await screen.findByLabelText(/^Название/);
  await userEvent.clear(title);
  await userEvent.type(title, "Django Backend Updated");
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить настройки" }),
  );

  expect(update).toHaveBeenCalledWith(
    "roadmap-id",
    expect.objectContaining({
      title: "Django Backend Updated",
    }),
  );
  expect(screen.getByText("Django ORM")).toBeInTheDocument();
  expect(screen.queryByLabelText(/Содержание/)).not.toBeInTheDocument();
});
