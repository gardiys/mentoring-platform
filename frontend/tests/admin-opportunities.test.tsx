import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AppLayout } from "../src/components/AppLayout";
import { workspaceApi } from "../src/features/opportunities/workspaceApi";
import { copilotApi } from "../src/features/copilot/api";
import { AdminOpportunitiesPage } from "../src/pages/AdminOpportunitiesPage";
import type {
  AdminConsultationRead,
  AdminOpportunitiesDashboard,
} from "../src/types/api";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

it("показывает администратору счётчик возможностей в меню", async () => {
  vi.spyOn(api, "me").mockResolvedValue({
    id: "admin-1",
    first_name: "Админ",
    last_name: null,
    telegram_id: 1,
    email: null,
    role: "admin",
    is_active: true,
    onboarding_completed_at: "2026-10-01T00:00:00Z",
  });
  vi.spyOn(api, "notifications").mockResolvedValue({
    items: [],
    unread_count: 0,
    total: 0,
    limit: 20,
    offset: 0,
  });
  vi.spyOn(copilotApi, "access").mockResolvedValue({
    allowed: true,
    student_allowed: true,
    students_enabled: true,
    learning_status: "active",
    reason: "",
  });
  vi.spyOn(workspaceApi, "summary").mockResolvedValue({
    needs_action_total: 7,
    overdue_total: 2,
    consultations: {},
    go_transition: {},
    python_repeat: {},
  });
  renderPage(<AppLayout />, "/admin/opportunities", "/admin/opportunities");
  expect(
    await screen.findByLabelText("Возможности требуют действия"),
  ).toHaveTextContent("7");
});

const student = {
  id: "student-1",
  first_name: "Иван",
  last_name: "Петров",
  telegram_username: "ivan",
  email: "student@example.com",
};
const mentor = {
  id: "mentor-1",
  first_name: "Антон",
  last_name: "Ментор",
  telegram_username: "mentor",
};
const consultation: AdminConsultationRead = {
  id: "consultation-1",
  student,
  mentor,
  consultation_type: "technical_mock",
  brief: "Подготовиться к техническому собеседованию",
  price_kopecks: 400_000,
  mentor_reward_kopecks: 250_000,
  duration_minutes: 60,
  status: "paid",
  scheduled_at: null,
  paid_at: "2026-10-15T10:00:00Z",
  completed_at: null,
  admin_note: null,
  written_summary: null,
  created_at: "2026-10-14T10:00:00Z",
};

function dashboardWith(item = consultation): AdminOpportunitiesDashboard {
  return {
    consultation_types: [],
    go_transition_description_markdown:
      "Описание программы перехода Python → Go",
    consultation_mentors: [{ ...mentor, is_enabled: true }],
    consultations: [item],
    go_transition_applications: [
      {
        id: "go-1",
        student,
        motivation: "Хочу перейти с Python на Go",
        status: "submitted",
        upfront_price_kopecks: 3_000_000,
        success_fee_percent: 100,
        approved_at: null,
        terms_accepted_at: null,
        paid_at: null,
        admin_note: null,
        terms_version: 1,
        terms_snapshot: {},
        terms_expires_at: null,
        accepted_terms_snapshot: null,
        created_at: "2026-10-14T10:00:00Z",
      },
    ],
  };
}

function openPage(dashboard: AdminOpportunitiesDashboard) {
  vi.spyOn(api, "adminOpportunities").mockResolvedValue(dashboard);
  return renderPage(
    <AdminOpportunitiesPage />,
    "/admin/opportunities",
    "/admin/opportunities",
  );
}

it.each(["paid", "scheduled"] as const)(
  "сохраняет набранные итог и комментарий и завершает консультацию %s",
  async (status) => {
    const user = userEvent.setup();
    const item = { ...consultation, status };
    const dashboard = dashboardWith(item);
    const update = vi
      .spyOn(api, "updateAdminConsultation")
      .mockResolvedValue(dashboardWith({ ...item, status: "completed" }));
    openPage(dashboard);

    const summaryInput = await screen.findByLabelText(
      "Краткий письменный итог",
    );
    const noteInput = screen.getByLabelText("Комментарий администратора");
    const complete = screen.getByRole("button", { name: "Завершить с итогом" });
    expect(complete).toBeDisabled();
    expect(
      screen.getByText("Ещё 10 символов, чтобы завершить"),
    ).toBeInTheDocument();
    expect(summaryInput).toHaveAttribute("maxlength", "10000");
    expect(noteInput).toHaveAttribute("maxlength", "5000");

    const summary = "И".repeat(40);
    const note = "К".repeat(20);
    await user.type(summaryInput, summary);
    await user.type(noteInput, note);
    expect(summaryInput).toHaveValue(summary);
    expect(noteInput).toHaveValue(note);
    expect(screen.getByText("40 / 10 000")).toBeInTheDocument();
    expect(complete).toBeEnabled();
    await user.click(complete);

    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(item.id, {
        status: "completed",
        mentor_id: mentor.id,
        scheduled_at: null,
        admin_note: note,
        written_summary: summary,
      }),
    );
  },
);

it("сохраняет набранный комментарий к решению по Go", async () => {
  const user = userEvent.setup();
  const dashboard = dashboardWith();
  const decide = vi
    .spyOn(api, "decideAdminGoTransition")
    .mockResolvedValue(dashboard);
  openPage(dashboard);

  const input = await screen.findByLabelText("Комментарий к решению");
  const note = "Р".repeat(20);
  await user.type(input, note);
  expect(input).toHaveValue(note);
  await user.click(screen.getByRole("button", { name: "Одобрить" }));
  await waitFor(() =>
    expect(decide).toHaveBeenCalledWith("go-1", {
      approved: true,
      admin_note: note,
    }),
  );
});

it.each([null, "Сохранённый ранее черновик"])(
  "планирует встречу, не публикуя набранный черновик итога (исходный итог: %s)",
  async (savedSummary) => {
    const user = userEvent.setup();
    const item = {
      ...consultation,
      admin_note: "Согласовали время с выпускником",
      written_summary: savedSummary,
    };
    const dashboard = dashboardWith(item);
    const update = vi
      .spyOn(api, "updateAdminConsultation")
      .mockResolvedValue(dashboard);
    openPage(dashboard);

    const summaryInput = await screen.findByLabelText(
      "Краткий письменный итог",
    );
    await user.clear(summaryInput);
    await user.type(summaryInput, "Незаконченный текст итога");
    fireEvent.change(screen.getByLabelText("Дата и время встречи"), {
      target: { value: "2026-10-20T15:30" },
    });
    await user.click(screen.getByRole("button", { name: "Запланировать" }));
    await waitFor(() =>
      expect(update).toHaveBeenCalledWith(item.id, {
        status: "scheduled",
        mentor_id: mentor.id,
        scheduled_at: new Date(2026, 9, 20, 15, 30).toISOString(),
        admin_note: item.admin_note,
        written_summary: savedSummary,
      }),
    );
  },
);
