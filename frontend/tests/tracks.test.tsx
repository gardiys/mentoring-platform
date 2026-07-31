import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminTrackForm } from "../src/features/admin/AdminTrackForm";
import { AdminTracksPage } from "../src/pages/AdminTracksPage";
import type { AdminTrackOptions, AdminTrackRead } from "../src/types/api";
import { renderPage } from "./render";

const pythonTrack: AdminTrackRead = {
  id: "40000000-0000-4000-8000-000000000001",
  slug: "python",
  title: "Python",
  description: "Трек Python Backend",
  position: 0,
  is_published: true,
  roadmaps: [
    {
      id: "30000000-0000-4000-8000-000000000001",
      slug: "python-backend",
      title: "Python Backend",
      is_published: true,
      position: 0,
    },
  ],
  student_ids: ["20000000-0000-4000-8000-000000000001"],
};

const options: AdminTrackOptions = {
  roadmaps: [
    ...pythonTrack.roadmaps,
    {
      id: "30000000-0000-4000-8000-000000000002",
      slug: "django-backend",
      title: "Django Backend",
      is_published: false,
      position: 1,
    },
  ],
  students: [
    {
      id: "20000000-0000-4000-8000-000000000001",
      first_name: "Иван",
      last_name: "Иванов",
      email: "student@example.com",
      telegram_id: 987654321,
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

it("показывает Python и количество назначений", async () => {
  vi.spyOn(api, "adminTracks").mockResolvedValue([pythonTrack]);
  renderPage(<AdminTracksPage />);

  expect(await screen.findByText("Python")).toBeInTheDocument();
  expect(
    screen.getByText(
      (_content, element) =>
        element?.tagName === "P" && element.textContent === "1 роадмапов",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByText(
      (_content, element) =>
        element?.tagName === "P" && element.textContent === "1 учеников",
    ),
  ).toBeInTheDocument();
});

it("добавляет роадмап в существующий трек", async () => {
  const update = vi
    .spyOn(api, "updateAdminTrack")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <AdminTrackForm track={pythonTrack} options={options} />,
    "/admin/tracks/40000000-0000-4000-8000-000000000001/edit",
    "/admin/tracks/:trackId/edit",
  );

  await userEvent.click(
    screen.getByRole("checkbox", { name: /Django Backend/ }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Сохранить трек" }));

  expect(update).toHaveBeenCalledWith(
    pythonTrack.id,
    expect.objectContaining({
      slug: "python",
      roadmap_ids: [pythonTrack.roadmaps[0]!.id, options.roadmaps[1]!.id],
    }),
  );
});

it("позволяет отозвать доступ ученика", async () => {
  const revoke = vi
    .spyOn(api, "revokeAdminTrackAccess")
    .mockResolvedValue(undefined);
  renderPage(<AdminTrackForm track={pythonTrack} options={options} />);

  await userEvent.click(screen.getByRole("checkbox", { name: /Иван Иванов/ }));

  expect(revoke).toHaveBeenCalledWith(pythonTrack.id, options.students[0]!.id);
});
