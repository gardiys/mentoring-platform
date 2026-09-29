import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { notifications } from "@mantine/notifications";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../src/api/endpoints";
import { MentorInterviewPage } from "../src/pages/MentorInterviewPage";
import type { MentorInterviewDetail } from "../src/types/api";
import { renderPage } from "./render";

const detail: MentorInterviewDetail = {
  process: {
    id: "process-1",
    company_name: "Оффер Тест",
    recruiter_telegram_usernames: [],
    track_id: "track-1",
    track_slug: "python",
    track_title: "Python",
    status: "active",
    close_reason: null,
    closed_at: null,
    stage_count: 0,
    next_stage_at: null,
    has_offer_file: false,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: "2026-09-01T00:00:00Z",
    can_delete: false,
    delete_locked_reason: "window_expired",
    deletable_until: "2026-09-02T00:00:00Z",
    offer: null,
    stages: [],
  },
  feedback: [],
};

function setup(
  role: "mentor" | "admin" | "student",
  status: "active" | "closed" | "offer" = "active",
) {
  vi.spyOn(api, "me").mockResolvedValue({
    id: "viewer",
    first_name: "Проверяющий",
    role,
    telegram_id: 1,
    last_name: null,
    email: null,
    onboarding_completed_at: "2026-09-01T00:00:00Z",
    is_active: true,
  });
  const initial = { ...detail, process: { ...detail.process, status } };
  const load = vi.spyOn(api, "mentorInterview").mockResolvedValue(initial);
  return { initial, load };
}
function openPage() {
  return renderPage(
    <MentorInterviewPage />,
    "/mentor/students/student-1/interviews/process-1",
    "/mentor/students/:studentId/interviews/:processId",
  );
}
afterEach(() => vi.restoreAllMocks());

it.each([
  ["mentor", "active"],
  ["mentor", "closed"],
  ["admin", "active"],
  ["admin", "closed"],
] as const)(
  "%s отмечает %s трек офферным одной кнопкой",
  async (role, status) => {
    const { load } = setup(role, status);
    const offered = {
      ...detail,
      process: { ...detail.process, status: "offer" as const },
    };
    const mark = vi
      .spyOn(api, "markMentorInterviewOffer")
      .mockImplementation(async () => {
        load.mockResolvedValue(offered);
        return offered;
      });
    openPage();
    await userEvent.click(
      await screen.findByRole("button", { name: "Отметить оффер" }),
    );
    await screen.findByText("Получен оффер");
    expect(mark).toHaveBeenCalledExactlyOnceWith("student-1", "process-1");
    expect(
      screen.queryByRole("button", { name: "Отметить оффер" }),
    ).not.toBeInTheDocument();
  },
);

it("сохраняет текущий статус и сообщает об ошибке запроса", async () => {
  setup("mentor");
  const notice = vi.spyOn(notifications, "show");
  vi.spyOn(api, "markMentorInterviewOffer").mockRejectedValue(
    new Error("Нет доступа к ученику"),
  );
  openPage();
  await userEvent.click(
    await screen.findByRole("button", { name: "Отметить оффер" }),
  );
  await waitFor(() =>
    expect(notice).toHaveBeenCalledWith(
      expect.objectContaining({
        color: "red",
        message: "Нет доступа к ученику",
      }),
    ),
  );
  expect(screen.getByText("Активный трек")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Отметить оффер" })).toBeEnabled();
});

it("не предлагает повторно отметить уже полученный оффер", async () => {
  setup("admin", "offer");
  openPage();
  await screen.findByText("Получен оффер");
  expect(
    screen.queryByRole("button", { name: "Отметить оффер" }),
  ).not.toBeInTheDocument();
});

it("не показывает менторское действие ученику", async () => {
  setup("student");
  openPage();
  await screen.findByText("Активный трек");
  expect(
    screen.queryByRole("button", { name: "Отметить оффер" }),
  ).not.toBeInTheDocument();
});
