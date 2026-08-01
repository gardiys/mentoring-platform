import { screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminMentorsPage } from "../src/pages/AdminMentorsPage";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

it("показывает менторов и защищает ментора с учениками от снятия роли", async () => {
  vi.spyOn(api, "adminMentors").mockResolvedValue([
    {
      id: "10000000-0000-4000-8000-000000000001",
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
});
