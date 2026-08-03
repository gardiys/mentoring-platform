import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminStudentForm } from "../src/features/admin/AdminStudentForm";
import { AdminStudentsPage } from "../src/pages/AdminStudentsPage";
import type {
  AdminStudentDetail,
  AdminStudentOptions,
  AdminStudentPage,
} from "../src/types/api";
import { renderPage } from "./render";

const mentor = {
  id: "10000000-0000-4000-8000-000000000001",
  role: "mentor" as const,
  first_name: "Антон",
  last_name: "Менторов",
  telegram_username: "mentor",
};

const adminMentor = {
  id: "10000000-0000-4000-8000-000000000002",
  role: "admin" as const,
  first_name: "Администратор",
  last_name: null,
  telegram_username: "admin",
};

const student: AdminStudentDetail = {
  id: "20000000-0000-4000-8000-000000000001",
  telegram_id: 987654321,
  first_name: "Иван",
  last_name: "Иванов",
  email: "student@example.com",
  is_active: true,
  created_at: "2026-08-01T10:00:00Z",
  learning_start_date: "2026-08-01",
  mentor,
  updated_at: "2026-08-01T10:00:00Z",
  onboarding_completed_at: "2026-08-01T10:00:00Z",
  last_progress_at: "2026-08-01T11:00:00Z",
  tracks: [
    {
      id: "40000000-0000-4000-8000-000000000001",
      slug: "python",
      title: "Python",
      is_published: true,
      granted_at: "2026-08-01T10:00:00Z",
    },
  ],
};

const options: AdminStudentOptions = {
  mentors: [mentor, adminMentor],
  tracks: [
    {
      id: student.tracks[0]!.id,
      slug: "python",
      title: "Python",
      is_published: true,
    },
    {
      id: "40000000-0000-4000-8000-000000000002",
      slug: "go",
      title: "Go",
      is_published: true,
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

it("показывает данные, треки и статус ученика в таблице", async () => {
  const page: AdminStudentPage = {
    items: [student],
    total: 1,
    limit: 50,
    offset: 0,
    mentors: [mentor],
  };
  vi.spyOn(api, "adminStudents").mockResolvedValue(page);

  renderPage(<AdminStudentsPage />);

  expect(await screen.findByText("Иван Иванов")).toBeInTheDocument();
  expect(screen.getByText("student@example.com")).toBeInTheDocument();
  expect(screen.getByText("Python")).toBeInTheDocument();
  expect(screen.getByText("Открыт")).toBeInTheDocument();
  expect(screen.getAllByLabelText("Ментор")[0]).toBeInTheDocument();
});

it("создаёт ученика с выбранным треком и администратором-ментором", async () => {
  const create = vi
    .spyOn(api, "createAdminStudent")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<AdminStudentForm options={options} />);

  await userEvent.type(screen.getByLabelText(/^Имя/), "Мария");
  await userEvent.type(screen.getByLabelText("Фамилия"), "Петрова");
  await userEvent.type(screen.getByLabelText("Email"), "maria@example.com");
  await userEvent.type(screen.getByLabelText(/Telegram ID/), "777000111");
  await userEvent.click(screen.getByRole("textbox", { name: /^Ментор/ }));
  await userEvent.click(screen.getByText("Администратор · администратор"));
  await userEvent.click(screen.getByRole("checkbox", { name: /Go/ }));
  await userEvent.click(
    screen.getByRole("button", { name: "Добавить ученика" }),
  );

  expect(create).toHaveBeenCalledWith({
    telegram_id: 777000111,
    first_name: "Мария",
    last_name: "Петрова",
    email: "maria@example.com",
    learning_start_date: expect.any(String),
    mentor_id: adminMentor.id,
    track_ids: [options.tracks[1]!.id],
  });
});

it("редактирует данные и закрывает доступ без удаления ученика", async () => {
  const update = vi
    .spyOn(api, "updateAdminStudent")
    .mockReturnValue(new Promise(() => undefined));
  const access = vi
    .spyOn(api, "setAdminStudentAccess")
    .mockResolvedValue({ ...student, is_active: false });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  renderPage(<AdminStudentForm options={options} student={student} />);

  const firstName = screen.getByLabelText(/^Имя/);
  await userEvent.clear(firstName);
  await userEvent.type(firstName, "Новое имя");
  const learningStartDate = screen.getByLabelText(/^Дата начала обучения/);
  await userEvent.clear(learningStartDate);
  await userEvent.type(learningStartDate, "2026-07-15");
  await userEvent.click(screen.getByRole("checkbox", { name: /Go/ }));
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить изменения" }),
  );

  expect(update).toHaveBeenCalledWith(
    student.id,
    expect.objectContaining({
      first_name: "Новое имя",
      learning_start_date: "2026-07-15",
      track_ids: [student.tracks[0]!.id, options.tracks[1]!.id],
    }),
  );

  await userEvent.click(screen.getByRole("button", { name: "Закрыть доступ" }));
  expect(window.confirm).toHaveBeenCalled();
  expect(access).toHaveBeenCalledWith(student.id, false);
});
