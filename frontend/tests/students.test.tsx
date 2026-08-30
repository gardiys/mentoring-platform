import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminStudentForm } from "../src/features/admin/AdminStudentForm";
import { AdminStudentsPage } from "../src/pages/AdminStudentsPage";
import type {
  AdminStudentDetail,
  AdminStudentOptions,
  AdminStudentPage,
} from "../src/types/api";
import { ADMIN_STUDENTS_FILTERS_STORAGE_KEY } from "../src/utils/studentListFilters";
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
  telegram_username: "ivan_student",
  first_name: "Иван",
  last_name: "Иванов",
  email: "student@example.com",
  is_active: true,
  learning_status: "learning",
  repayment_percent: 200,
  mentor_reward_percent: 40,
  entry_payment_kopecks: 4_500_000,
  entry_payment_paid_at: "2026-08-01T10:00:00Z",
  program_excluded_at: null,
  program_exclusion_reason: null,
  public_identity_hidden_at: null,
  public_identity_hidden_reason: null,
  personal_data_erased_at: null,
  personal_data_erasure_reason: null,
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

beforeEach(() => {
  window.localStorage.removeItem(ADMIN_STUDENTS_FILTERS_STORAGE_KEY);
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.removeItem(ADMIN_STUDENTS_FILTERS_STORAGE_KEY);
});

async function selectOption(label: string, option: string) {
  const input = screen
    .getAllByLabelText(label)
    .find((element) => element.tagName === "INPUT");
  expect(input).toBeDefined();
  await userEvent.click(input!);
  await waitFor(() => expect(input!).toHaveAttribute("aria-controls"));
  const listbox = document.getElementById(
    input!.getAttribute("aria-controls")!,
  );
  expect(listbox).not.toBeNull();
  await userEvent.click(within(listbox!).getByText(option));
}

it("показывает данные, треки и статус ученика в таблице", async () => {
  const page: AdminStudentPage = {
    items: [student],
    total: 1,
    limit: 50,
    offset: 0,
    mentors: [mentor],
    tracks: options.tracks,
  };
  const list = vi.spyOn(api, "adminStudents").mockResolvedValue(page);

  renderPage(<AdminStudentsPage />);

  expect(await screen.findByText("Иван Иванов")).toBeInTheDocument();
  expect(screen.getByText("student@example.com")).toBeInTheDocument();
  expect(screen.getByText("@ivan_student")).toBeInTheDocument();
  expect(screen.getAllByText("Python").length).toBeGreaterThan(0);
  expect(screen.getByText("Открыт")).toBeInTheDocument();
  expect(screen.getAllByText("Учится").length).toBeGreaterThan(0);
  expect(screen.getAllByLabelText("Ментор")[0]).toBeInTheDocument();
  expect(screen.getAllByLabelText("Направление")[0]).toBeInTheDocument();
  expect(screen.getAllByLabelText("Текущий статус")[0]).toBeInTheDocument();
  expect(screen.getAllByLabelText("Доступ")[0]).toHaveValue("Доступ открыт");
  expect(screen.getByText("Найдено учеников: 1")).toBeInTheDocument();
  await waitFor(() =>
    expect(list).toHaveBeenCalledWith(
      expect.objectContaining({ isActive: true }),
    ),
  );

  await userEvent.type(screen.getByLabelText("Поиск"), "Иван");
  await selectOption("Направление", "Python");
  await selectOption("Текущий статус", "Учится");
  await selectOption("Доступ", "Доступ закрыт");
  await selectOption("Ментор", "Антон Менторов");

  await waitFor(() =>
    expect(list).toHaveBeenLastCalledWith({
      query: "Иван",
      trackId: student.tracks[0]!.id,
      learningStatuses: ["learning"],
      isActive: false,
      mentorId: mentor.id,
      withoutMentor: false,
      limit: 50,
      offset: 0,
    }),
  );
  await waitFor(() =>
    expect(
      JSON.parse(
        window.localStorage.getItem(ADMIN_STUDENTS_FILTERS_STORAGE_KEY) ?? "{}",
      ),
    ).toEqual({
      search: "Иван",
      trackId: student.tracks[0]!.id,
      statuses: ["learning"],
      access: "blocked",
      mentorFilter: mentor.id,
      sort: "name_asc",
    }),
  );
});

it("восстанавливает фильтры раздела учеников из браузера", async () => {
  window.localStorage.setItem(
    ADMIN_STUDENTS_FILTERS_STORAGE_KEY,
    JSON.stringify({
      search: "Иван",
      trackId: student.tracks[0]!.id,
      statuses: ["learning", "interviewing"],
      access: "all",
      mentorFilter: "unassigned",
    }),
  );
  const page: AdminStudentPage = {
    items: [],
    total: 0,
    limit: 50,
    offset: 0,
    mentors: [mentor],
    tracks: options.tracks,
  };
  const list = vi.spyOn(api, "adminStudents").mockResolvedValue(page);

  renderPage(<AdminStudentsPage />);

  expect(await screen.findByLabelText("Поиск")).toHaveValue("Иван");
  await waitFor(() =>
    expect(
      screen
        .getAllByLabelText("Направление")
        .find((element) => element.tagName === "INPUT"),
    ).toHaveValue("Python"),
  );
  expect(
    screen
      .getAllByLabelText("Доступ")
      .find((element) => element.tagName === "INPUT"),
  ).toHaveValue("Любой доступ");
  expect(
    screen
      .getAllByLabelText("Ментор")
      .find((element) => element.tagName === "INPUT"),
  ).toHaveValue("Без ментора");
  await waitFor(() =>
    expect(list).toHaveBeenLastCalledWith({
      query: "Иван",
      trackId: student.tracks[0]!.id,
      learningStatuses: ["learning", "interviewing"],
      isActive: null,
      mentorId: null,
      withoutMentor: true,
      limit: 50,
      offset: 0,
    }),
  );
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
  await userEvent.type(
    screen.getByLabelText("Telegram username"),
    "  @@maria_dev  ",
  );
  await userEvent.click(screen.getByRole("textbox", { name: /^Ментор/ }));
  await userEvent.click(screen.getByText("Администратор · администратор"));
  await userEvent.click(screen.getByRole("checkbox", { name: /Go/ }));
  await userEvent.click(
    screen.getByRole("button", { name: "Добавить ученика" }),
  );

  expect(create).toHaveBeenCalledWith({
    telegram_id: 777000111,
    telegram_username: "maria_dev",
    first_name: "Мария",
    last_name: "Петрова",
    email: "maria@example.com",
    learning_start_date: expect.any(String),
    mentor_id: adminMentor.id,
    repayment_percent: 200,
    mentor_reward_percent: 45,
    entry_payment_rubles: 45_000,
    entry_payment_paid: false,
    program_excluded: false,
    program_exclusion_reason: null,
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
  const telegramUsername = screen.getByLabelText("Telegram username");
  await userEvent.clear(telegramUsername);
  await userEvent.type(telegramUsername, "@ivan_updated");
  await userEvent.click(screen.getByRole("checkbox", { name: /Go/ }));
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить изменения" }),
  );

  expect(update).toHaveBeenCalledWith(
    student.id,
    expect.objectContaining({
      first_name: "Новое имя",
      telegram_username: "ivan_updated",
      learning_start_date: "2026-07-15",
      track_ids: [student.tracks[0]!.id, options.tracks[1]!.id],
    }),
  );

  await userEvent.click(screen.getByRole("button", { name: "Закрыть доступ" }));
  expect(window.confirm).toHaveBeenCalled();
  expect(access).toHaveBeenCalledWith(student.id, false);
});
