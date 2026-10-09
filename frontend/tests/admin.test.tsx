import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminRoadmapCreatePage } from "../src/pages/AdminRoadmapCreatePage";
import { AdminRoadmapEditPage } from "../src/pages/AdminRoadmapEditPage";
import { AdminRoadmapSectionEditPage } from "../src/pages/AdminRoadmapSectionEditPage";
import { AdminRoadmapsPage } from "../src/pages/AdminRoadmapsPage";
import type {
  AdminRoadmapOutline,
  AdminRoadmapRead,
  AdminRoadmapSummary,
  AdminSectionOutline,
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

const sectionOutline: AdminSectionOutline = {
  id: "section-id",
  title: "Django",
  description: null,
  position: 0,
  duration_days: null,
  topics: [],
};

it("AdminRoadmapsPage показывает черновики", async () => {
  vi.spyOn(api, "adminRoadmapSummaries").mockResolvedValue([summary]);
  renderPage(<AdminRoadmapsPage />);

  expect(await screen.findByText("Django Backend")).toBeInTheDocument();
  expect(screen.getByText("Черновик")).toBeInTheDocument();
});

it("удаляет роадмап только после подтверждения", async () => {
  vi.spyOn(api, "adminRoadmapSummaries").mockResolvedValue([summary]);
  const remove = vi
    .spyOn(api, "deleteAdminRoadmap")
    .mockReturnValue(new Promise(() => undefined));
  vi.spyOn(window, "confirm")
    .mockReturnValueOnce(false)
    .mockReturnValueOnce(true);

  renderPage(<AdminRoadmapsPage />);

  const deleteButton = await screen.findByRole("button", { name: "Удалить" });
  await userEvent.click(deleteButton);
  expect(remove).not.toHaveBeenCalled();

  await userEvent.click(deleteButton);
  expect(remove).toHaveBeenCalledOnce();
  expect(remove.mock.calls[0]?.[0]).toBe(summary.id);
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

it("создаёт раздел роадмапа через отдельную форму", async () => {
  const read = vi.spyOn(api, "adminRoadmapSection");
  const create = vi
    .spyOn(api, "createAdminRoadmapSection")
    .mockResolvedValue({ ...sectionOutline, id: "new-section-id" });
  const { router } = renderPage(
    <AdminRoadmapSectionEditPage />,
    "/admin/roadmaps/roadmap-id/sections/new",
    "/admin/roadmaps/:roadmapId/sections/new",
  );

  expect(
    screen.getByRole("heading", { name: "Новый раздел" }),
  ).toBeInTheDocument();
  expect(read).not.toHaveBeenCalled();
  await userEvent.type(screen.getByLabelText(/^Название/), "Новый раздел");
  await userEvent.type(screen.getByLabelText(/^Описание/), "Описание раздела");
  const position = screen.getByLabelText(/^Позиция/);
  await userEvent.clear(position);
  await userEvent.type(position, "2");
  await userEvent.type(screen.getByLabelText(/^Длительность/), "7");
  await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(create).toHaveBeenCalledWith("roadmap-id", {
    title: "Новый раздел",
    description: "Описание раздела",
    position: 2,
    duration_days: 7,
  });
  await waitFor(() =>
    expect(router.state.location.pathname).toBe(
      "/admin/roadmaps/roadmap-id/edit",
    ),
  );
});

it("редактирует раздел и позволяет очистить описание", async () => {
  const section = { ...sectionOutline, description: "Старое описание" };
  vi.spyOn(api, "adminRoadmapSection").mockResolvedValue(section);
  const create = vi.spyOn(api, "createAdminRoadmapSection");
  const update = vi
    .spyOn(api, "updateAdminRoadmapSection")
    .mockResolvedValue(section);
  const { router } = renderPage(
    <AdminRoadmapSectionEditPage />,
    "/admin/roadmaps/roadmap-id/sections/section-id/edit",
    "/admin/roadmaps/:roadmapId/sections/:sectionId/edit",
  );

  const title = await screen.findByLabelText(/^Название/);
  expect(title).toHaveValue("Django");
  await userEvent.clear(title);
  await userEvent.type(title, "Обновлённый раздел");
  const description = screen.getByLabelText(/^Описание/);
  await userEvent.clear(description);
  await userEvent.type(description, "Новое описание");
  await userEvent.clear(description);
  await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(create).not.toHaveBeenCalled();
  expect(update).toHaveBeenCalledWith("roadmap-id", "section-id", {
    title: "Обновлённый раздел",
    description: null,
    position: section.position,
    duration_days: section.duration_days,
  });
  await waitFor(() =>
    expect(router.state.location.pathname).toBe(
      "/admin/roadmaps/roadmap-id/edit",
    ),
  );
});
