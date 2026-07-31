import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminRoadmapCreatePage } from "../src/pages/AdminRoadmapCreatePage";
import { AdminRoadmapEditPage } from "../src/pages/AdminRoadmapEditPage";
import { AdminRoadmapsPage } from "../src/pages/AdminRoadmapsPage";
import type { AdminRoadmapRead } from "../src/types/api";
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
        },
      ],
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

it("AdminRoadmapsPage показывает черновики", async () => {
  vi.spyOn(api, "adminRoadmaps").mockResolvedValue([created]);
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

it("редактор сохраняет изменения с UUID существующих тем", async () => {
  vi.spyOn(api, "adminRoadmap").mockResolvedValue(created);
  const update = vi
    .spyOn(api, "updateAdminRoadmap")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <AdminRoadmapEditPage />,
    "/admin/roadmaps/roadmap-id/edit",
    "/admin/roadmaps/:roadmapId/edit",
  );

  const title = await screen.findByLabelText(/^Название роадмапа/);
  await userEvent.clear(title);
  await userEvent.type(title, "Django Backend Updated");
  expect(
    screen.getByRole("button", { name: "Удалить раздел 1" }),
  ).toBeDisabled();
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить изменения" }),
  );

  expect(update).toHaveBeenCalledWith(
    "roadmap-id",
    expect.objectContaining({
      title: "Django Backend Updated",
      sections: [
        expect.objectContaining({
          id: "section-id",
          topics: [expect.objectContaining({ id: "topic-id" })],
        }),
      ],
    }),
  );
});
