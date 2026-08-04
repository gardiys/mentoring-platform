import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminMentorsPage } from "../src/pages/AdminMentorsPage";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

it("показывает менторов и защищает ментора с учениками от снятия роли", async () => {
  vi.spyOn(api, "adminMentors").mockResolvedValue([
    {
      id: "10000000-0000-4000-8000-000000000001",
      role: "mentor",
      telegram_id: 100500,
      telegram_username: "mentor",
      first_name: "Антон",
      last_name: null,
      email: "mentor@example.com",
      is_active: true,
      student_count: 3,
      tracks: [
        {
          id: "30000000-0000-4000-8000-000000000001",
          slug: "python",
          title: "Python",
        },
      ],
      students: [
        {
          id: "20000000-0000-4000-8000-000000000001",
          first_name: "Иван",
          last_name: null,
          telegram_username: "ivan",
        },
      ],
      created_at: "2026-08-01T00:00:00Z",
    },
    {
      id: "10000000-0000-4000-8000-000000000002",
      role: "admin",
      telegram_id: 100501,
      telegram_username: "admin",
      first_name: "Администратор",
      last_name: null,
      email: "admin@example.com",
      is_active: true,
      student_count: 0,
      tracks: [
        {
          id: "30000000-0000-4000-8000-000000000001",
          slug: "python",
          title: "Python",
        },
      ],
      students: [],
      created_at: "2026-08-01T00:00:00Z",
    },
  ]);
  vi.spyOn(api, "adminMentorCandidates").mockResolvedValue([]);
  vi.spyOn(api, "adminStudentOptions").mockResolvedValue({
    tracks: [
      {
        id: "30000000-0000-4000-8000-000000000001",
        slug: "python",
        title: "Python",
        is_published: true,
      },
    ],
    mentors: [],
  });
  const updateProfile = vi
    .spyOn(api, "updateAdminMentorProfile")
    .mockReturnValue(new Promise(() => undefined));

  renderPage(<AdminMentorsPage />, "/admin/mentors", "/admin/mentors");

  expect(
    await screen.findByRole("heading", { name: "Антон" }),
  ).toBeInTheDocument();
  expect(screen.getByText("3 учеников")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Убрать из менторов" }),
  ).toBeDisabled();
  expect(
    screen.getByText("Перед удалением роли переназначьте учеников."),
  ).toBeInTheDocument();
  expect(screen.getByText("Администратор · ментор")).toBeInTheDocument();
  expect(
    screen.getByText(
      "Основная роль администратора сохраняется и не может быть снята из этого раздела.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getAllByRole("button", { name: "Убрать из менторов" }),
  ).toHaveLength(1);

  await userEvent.click(
    screen.getAllByRole("button", { name: "Редактировать данные" })[1]!,
  );
  const username = await screen.findByLabelText("Telegram username ментора");
  await userEvent.clear(username);
  await userEvent.type(username, "  @@platform_admin  ");
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить данные" }),
  );

  await waitFor(() =>
    expect(updateProfile).toHaveBeenCalledWith(
      "10000000-0000-4000-8000-000000000002",
      {
        first_name: "Администратор",
        last_name: null,
        email: "admin@example.com",
        telegram_username: "platform_admin",
      },
    ),
  );
});
