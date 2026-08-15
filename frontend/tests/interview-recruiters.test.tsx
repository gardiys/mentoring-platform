import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { InterviewRecruitersPage } from "../src/pages/InterviewRecruitersPage";
import type { RecruiterContactRead } from "../src/types/api";
import { renderPage } from "./render";

const student = {
  id: "20000000-0000-4000-8000-000000000001",
  telegram_id: 987654321,
  first_name: "Иван",
  last_name: null,
  email: null,
  role: "student" as const,
  onboarding_completed_at: "2026-08-01T00:00:00Z",
  is_active: true,
};

const recruiter: RecruiterContactRead = {
  id: "81000000-0000-4000-8000-000000000001",
  telegram_username: "yandex_recruiter",
  companies: [{ id: "82000000-0000-4000-8000-000000000001", name: "Яндекс" }],
  tracks: [
    {
      id: "30000000-0000-4000-8000-000000000001",
      slug: "python",
      title: "Python",
    },
  ],
  total_contact_opens: 12,
  students_contacted_count: 8,
  last_contacted_at: "2026-08-15T10:00:00Z",
  helpful_count: 5,
  ignores_count: 1,
  no_longer_works_count: 0,
  account_missing_count: 0,
  other_issue_count: 0,
  issue_comments: [
    {
      author_id: "20000000-0000-4000-8000-000000000002",
      author_first_name: "Мария",
      author_telegram_username: "maria_dev",
      author_role: "student",
      kind: "ignores",
      reason: "Не отвечает две недели",
      updated_at: "2026-08-15T11:00:00Z",
    },
  ],
  issue_comments_total: 1,
  has_contacted: false,
  my_contact_opens: 0,
  my_last_contacted_at: null,
  my_feedback: null,
};

const groupedRecruiters = [
  {
    company: recruiter.companies[0]!,
    recruiters: [recruiter],
  },
];

afterEach(() => vi.restoreAllMocks());

it("показывает статистику рекрутера и сохраняет положительную оценку", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "interviewCatalogDirections").mockResolvedValue([
    { id: recruiter.tracks[0]!.id, slug: "python", title: "Python" },
  ]);
  vi.spyOn(api, "interviewRecruiters").mockResolvedValue({
    items: groupedRecruiters,
    total: 1,
    limit: 24,
    offset: 0,
  });
  const save = vi.spyOn(api, "setRecruiterFeedback").mockResolvedValue({
    kind: "helpful",
    reason: null,
    updated_at: "2026-08-15T12:00:00Z",
  });
  vi.spyOn(window, "open").mockReturnValue({
    opener: null,
    closed: false,
    location: { replace: vi.fn() },
  } as unknown as Window);
  vi.spyOn(api, "openRecruiterContact").mockResolvedValue({
    recruiter_id: recruiter.id,
    url: "https://t.me/yandex_recruiter",
    total_contact_opens: 13,
    students_contacted_count: 9,
    last_contacted_at: "2026-08-15T12:30:00Z",
    my_contact_opens: 1,
    my_last_contacted_at: "2026-08-15T12:30:00Z",
  });

  renderPage(
    <InterviewRecruitersPage />,
    "/interviews/recruiters",
    "/interviews/recruiters",
  );

  expect(await screen.findByText("@yandex_recruiter")).toBeInTheDocument();
  expect(
    screen.getByText("12 пользователей открыли контакт"),
  ).toBeInTheDocument();
  expect(screen.getByText("Из них учеников: 8")).toBeInTheDocument();
  expect(screen.getByText("Комментарии к проблемам")).toBeInTheDocument();
  expect(screen.getByText("Не отвечает две недели")).toBeInTheDocument();
  expect(screen.getByText(/Мария · @maria_dev · Ученик/)).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Яндекс" })).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Написать в Telegram ↗" }),
  );
  expect(
    await screen.findByText("13 пользователей открыли контакт"),
  ).toBeInTheDocument();
  expect(screen.getByText("Вы открывали этот контакт")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Хороший контакт" }),
  );

  await waitFor(() =>
    expect(save).toHaveBeenCalledWith(recruiter.id, {
      kind: "helpful",
      reason: null,
    }),
  );
});

it.each(["mentor", "admin"] as const)(
  "позволяет роли %s оценивать рекрутера",
  async (role) => {
    vi.spyOn(api, "me").mockResolvedValue({ ...student, role });
    vi.spyOn(api, "interviewCatalogDirections").mockResolvedValue([]);
    vi.spyOn(api, "interviewRecruiters").mockResolvedValue({
      items: groupedRecruiters,
      total: 1,
      limit: 24,
      offset: 0,
    });

    renderPage(
      <InterviewRecruitersPage />,
      "/interviews/recruiters",
      "/interviews/recruiters",
    );

    expect(
      await screen.findByRole("button", { name: "Хороший контакт" }),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Сообщить о проблеме" }),
    ).toBeVisible();
  },
);

it("позволяет сообщить о неактуальном контакте", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "interviewCatalogDirections").mockResolvedValue([]);
  vi.spyOn(api, "interviewRecruiters").mockResolvedValue({
    items: groupedRecruiters,
    total: 1,
    limit: 24,
    offset: 0,
  });
  const save = vi.spyOn(api, "setRecruiterFeedback").mockResolvedValue({
    kind: "ignores",
    reason: "Не отвечает две недели",
    updated_at: "2026-08-15T12:00:00Z",
  });

  renderPage(
    <InterviewRecruitersPage />,
    "/interviews/recruiters",
    "/interviews/recruiters",
  );
  await userEvent.click(
    await screen.findByRole("button", { name: "Сообщить о проблеме" }),
  );
  const dialog = await screen.findByRole("dialog");
  await userEvent.type(
    within(dialog).getByRole("textbox", {
      name: "Комментарий — необязательно",
    }),
    "Не отвечает две недели",
  );
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Сохранить отметку" }),
  );

  await waitFor(() =>
    expect(save).toHaveBeenCalledWith(recruiter.id, {
      kind: "ignores",
      reason: "Не отвечает две недели",
    }),
  );
});
