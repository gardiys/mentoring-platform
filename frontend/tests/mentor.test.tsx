import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { MentorStudentPage } from "../src/pages/MentorStudentPage";
import { MentorStudentsPage } from "../src/pages/MentorStudentsPage";
import { MentorInterviewPage } from "../src/pages/MentorInterviewPage";
import type {
  MentorInterviewDetail,
  MentorStudentDetail,
} from "../src/types/api";
import { STUDENT_PROGRESS_FILTERS_STORAGE_KEY } from "../src/utils/studentListFilters";
import { renderPage } from "./render";

beforeEach(() => {
  window.localStorage.removeItem(STUDENT_PROGRESS_FILTERS_STORAGE_KEY);
});

afterEach(() => {
  vi.restoreAllMocks();
  window.localStorage.removeItem(STUDENT_PROGRESS_FILTERS_STORAGE_KEY);
});

it("MentorStudentsPage отображает учеников", async () => {
  const updateState = vi
    .spyOn(api, "updateMentorStudentState")
    .mockResolvedValue({} as MentorStudentDetail);
  const students = vi.spyOn(api, "mentorStudents").mockResolvedValue({
    items: [
      {
        id: "u1",
        first_name: "Иван",
        last_name: "Иванов",
        email: "student@example.com",
        telegram_username: "  @@ivan_student  ",
        learning_start_date: "2026-07-01",
        is_active: true,
        learning_status: "learning",
        strength_level: null,
        roadmaps: [],
        current_topics: [],
        last_progress_at: "2026-08-10T10:00:00Z",
        last_activity_kind: "interview",
        completed_topics_this_week: 0,
        is_overdue: false,
        mock_interview_count: 0,
      },
      {
        id: "u2",
        first_name: "Мария",
        last_name: null,
        email: null,
        telegram_username: null,
        learning_start_date: null,
        is_active: false,
        learning_status: "learning",
        strength_level: null,
        roadmaps: [],
        current_topics: [],
        last_progress_at: null,
        last_activity_kind: null,
        completed_topics_this_week: 0,
        is_overdue: false,
        mock_interview_count: 0,
      },
    ],
    total: 2,
    limit: 25,
    offset: 0,
    directions: [{ id: "python", slug: "python", title: "Python" }],
    mentors: [
      {
        id: "mentor-1",
        role: "mentor",
        first_name: "Антон",
        last_name: "Менторов",
        telegram_username: "mentor",
      },
      {
        id: "admin-1",
        role: "admin",
        first_name: "Администратор",
        last_name: null,
        telegram_username: "admin",
      },
    ],
    can_filter_by_mentor: true,
  });
  renderPage(<MentorStudentsPage />);
  expect(await screen.findByText("Иван Иванов")).toBeInTheDocument();
  expect(screen.getAllByLabelText("Направление")[0]).toBeInTheDocument();
  expect(screen.getAllByLabelText("Текущий статус")[0]).toBeInTheDocument();
  expect(screen.getAllByLabelText("Доступ")[0]).toHaveValue("Доступ открыт");
  expect(screen.getAllByLabelText("Ментор")[0]).toBeInTheDocument();
  expect(screen.getAllByLabelText("Сортировка")[0]).toHaveValue("По имени");
  expect(screen.getByText("Найдено учеников: 2")).toBeInTheDocument();
  expect(screen.getByText(/Собеседования ·/)).toBeInTheDocument();
  expect(screen.getByText("01.07.2026")).toBeInTheDocument();
  expect(screen.getAllByText("Доступ закрыт").length).toBeGreaterThan(0);
  await waitFor(() =>
    expect(students).toHaveBeenCalledWith(
      expect.objectContaining({ isActive: true }),
    ),
  );
  const accessInput = screen.getAllByLabelText("Доступ")[0]!;
  await userEvent.click(accessInput);
  await waitFor(() => expect(accessInput).toHaveAttribute("aria-controls"));
  const accessOptions = document.getElementById(
    accessInput.getAttribute("aria-controls")!,
  );
  expect(accessOptions).not.toBeNull();
  await userEvent.click(within(accessOptions!).getByText("Доступ закрыт"));
  await waitFor(() =>
    expect(students).toHaveBeenLastCalledWith(
      expect.objectContaining({ isActive: false }),
    ),
  );
  await waitFor(() =>
    expect(
      JSON.parse(
        window.localStorage.getItem(STUDENT_PROGRESS_FILTERS_STORAGE_KEY) ??
          "{}",
      ),
    ).toEqual(expect.objectContaining({ access: "blocked" })),
  );
  await userEvent.click(screen.getAllByLabelText("Ментор")[0]!);
  expect(
    await screen.findByText("Администратор · администратор"),
  ).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  const telegramLink = screen.getByRole("link", {
    name: "Написать в Telegram · @ivan_student",
  });
  expect(telegramLink).toHaveAttribute("href", "https://t.me/ivan_student");
  expect(telegramLink).toHaveAttribute("target", "_blank");
  expect(telegramLink).toHaveAttribute("rel", "noopener noreferrer");
  expect(screen.getByText("Telegram не указан")).toBeInTheDocument();
  const statusInput = screen
    .getAllByLabelText("Статус ученика Иван Иванов")
    .find((element) => element.tagName === "INPUT")!;
  await userEvent.click(statusInput);
  await waitFor(() => expect(statusInput).toHaveAttribute("aria-controls"));
  const statusOptions = document.getElementById(
    statusInput.getAttribute("aria-controls")!,
  );
  expect(statusOptions).not.toBeNull();
  await userEvent.click(
    within(statusOptions!).getByText("Ходит на собеседования"),
  );
  await waitFor(() =>
    expect(updateState).toHaveBeenCalledWith("u1", "interviewing", null),
  );
});

it("показывает аналитику собеседований и переключает период", async () => {
  vi.spyOn(api, "mentorStudents").mockResolvedValue({
    items: [],
    total: 2,
    limit: 25,
    offset: 0,
    directions: [{ id: "python", slug: "python", title: "Python" }],
    mentors: [],
    can_filter_by_mentor: false,
  });
  const analytics = vi
    .spyOn(api, "mentorInterviewAnalytics")
    .mockResolvedValue({
      period: "week",
      period_start: "2026-08-08T00:00:00Z",
      period_end: "2026-08-15T00:00:00Z",
      selected_student_count: 2,
      current_interviewing_students: 2,
      students_with_interviews: 2,
      students_without_interviews: 0,
      total_interviews: 8,
      unique_companies: 5,
      active_processes: 4,
      offers_received: 1,
      ai_analyses_started: 3,
      ai_analyses_ready: 2,
      ai_analyses_failed: 1,
      interviews_with_recording: 4,
      upcoming_interviews_next_week: 2,
      average_interviews_per_participant: 4,
      offer_conversion_percent: 20,
      ai_success_rate_percent: 66.7,
      recording_coverage_percent: 50,
      stage_counts: [
        { stage_type: "screening", count: 3 },
        { stage_type: "technical_screening", count: 1 },
        { stage_type: "technical_interview", count: 2 },
        { stage_type: "system_design", count: 0 },
        { stage_type: "final_interview", count: 1 },
        { stage_type: "other", count: 1 },
      ],
      ranking: [
        {
          position: 1,
          student_id: "u1",
          first_name: "Иван",
          last_name: "Иванов",
          telegram_username: "ivan",
          interview_count: 5,
          company_count: 3,
          offer_count: 1,
          ai_analysis_count: 2,
          last_interview_at: "2026-08-14T10:00:00Z",
        },
      ],
    });

  renderPage(<MentorStudentsPage />);
  await userEvent.click(
    await screen.findByRole("tab", { name: "Аналитика собеседований" }),
  );

  expect(await screen.findByText("Рейтинг активности")).toBeInTheDocument();
  expect(screen.getByText("Офферов получено")).toBeInTheDocument();
  expect(screen.getByText("Технические интервью")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Иван Иванов" })).toHaveAttribute(
    "href",
    "/mentor/students/u1",
  );
  await waitFor(() =>
    expect(analytics).toHaveBeenLastCalledWith(
      expect.objectContaining({ period: "week", isActive: true }),
    ),
  );

  await userEvent.click(screen.getByText("Последние 30 дней"));
  await waitFor(() =>
    expect(analytics).toHaveBeenLastCalledWith(
      expect.objectContaining({ period: "month" }),
    ),
  );
});

it("показывает администратору эффективность менторов", async () => {
  vi.spyOn(api, "mentorStudents").mockResolvedValue({
    items: [],
    total: 4,
    limit: 25,
    offset: 0,
    directions: [{ id: "python", slug: "python", title: "Python" }],
    mentors: [
      {
        id: "mentor-1",
        role: "mentor",
        first_name: "Антон",
        last_name: "Менторов",
        telegram_username: "mentor",
      },
    ],
    can_filter_by_mentor: true,
  });
  const efficiency = vi
    .spyOn(api, "mentorEfficiencyAnalytics")
    .mockResolvedValue({
      period: "week",
      period_start: "2026-08-08T00:00:00Z",
      period_end: "2026-08-15T00:00:00Z",
      mentor_count: 1,
      assigned_students: 4,
      interviewing_students: 3,
      active_interviewing_students: 2,
      inactive_interviewing_students: 1,
      unassigned_students: 1,
      unassigned_interviewing_students: 1,
      mentors: [
        {
          mentor_id: "mentor-1",
          role: "mentor",
          first_name: "Антон",
          last_name: "Менторов",
          telegram_username: "mentor",
          assigned_students: 3,
          interviewing_students: 2,
          active_interviewing_students: 1,
          recording_students: 1,
          inactive_interviewing_students: 1,
          interview_count: 4,
          recording_count: 2,
          ai_analysis_count: 1,
          offer_count: 1,
          upcoming_students: 1,
          participation_percent: 50,
          recording_participation_percent: 100,
          average_interviews_per_active_student: 4,
          last_interview_at: "2026-08-14T10:00:00Z",
        },
      ],
    });

  renderPage(<MentorStudentsPage />);
  await userEvent.click(
    await screen.findByRole("tab", { name: "Эффективность менторов" }),
  );

  expect(
    await screen.findByRole("heading", { name: "Эффективность менторов" }),
  ).toBeInTheDocument();
  expect(screen.getAllByText("Реально активны")).toHaveLength(2);
  expect(screen.getByText("Ученики без ментора")).toBeInTheDocument();
  expect(screen.getByText("Антон Менторов")).toBeInTheDocument();
  expect(screen.getByText("1 из 2")).toBeInTheDocument();
  await waitFor(() =>
    expect(efficiency).toHaveBeenLastCalledWith({
      period: "week",
      trackId: null,
      isActive: true,
    }),
  );
});

it("восстанавливает фильтры прогресса после повторного открытия", async () => {
  window.localStorage.setItem(
    STUDENT_PROGRESS_FILTERS_STORAGE_KEY,
    JSON.stringify({
      search: "Мария",
      trackId: "go",
      statuses: ["learning", "interviewing"],
      access: "blocked",
      mentorFilter: "mentor-1",
      sort: "learning_start_asc",
    }),
  );
  const students = vi.spyOn(api, "mentorStudents").mockResolvedValue({
    items: [],
    total: 0,
    limit: 12,
    offset: 0,
    directions: [{ id: "go", slug: "go", title: "Go" }],
    mentors: [
      {
        id: "mentor-1",
        role: "mentor",
        first_name: "Антон",
        last_name: "Менторов",
        telegram_username: "mentor",
      },
    ],
    can_filter_by_mentor: true,
  });

  renderPage(<MentorStudentsPage />);

  expect(await screen.findByLabelText("Поиск")).toHaveValue("Мария");
  expect(
    screen
      .getAllByLabelText("Направление")
      .find((element) => element.tagName === "INPUT"),
  ).toHaveValue("Go");
  expect(
    screen
      .getAllByLabelText("Доступ")
      .find((element) => element.tagName === "INPUT"),
  ).toHaveValue("Доступ закрыт");
  expect(
    screen
      .getAllByLabelText("Ментор")
      .find((element) => element.tagName === "INPUT"),
  ).toHaveValue("Антон Менторов");
  expect(
    screen
      .getAllByLabelText("Сортировка")
      .find((element) => element.tagName === "INPUT"),
  ).toHaveValue("Старт обучения: ранние сначала");
  await waitFor(() =>
    expect(students).toHaveBeenLastCalledWith({
      query: "Мария",
      trackId: "go",
      mentorId: "mentor-1",
      withoutMentor: false,
      isActive: false,
      learningStatuses: ["learning", "interviewing"],
      sort: "learning_start_asc",
      limit: 25,
      offset: 0,
    }),
  );
});

it("показывает Telegram-чат в детальной карточке ученика", async () => {
  const student: MentorStudentDetail = {
    id: "student-1",
    first_name: "Иван",
    last_name: "Иванов",
    email: "student@example.com",
    telegram_username: "@ivan_detail",
    learning_start_date: "2026-07-01",
    is_active: true,
    learning_status: "learning",
    strength_level: null,
    roadmaps: [],
    current_topics: [],
    last_progress_at: null,
    last_activity_kind: null,
    completed_topics_this_week: 0,
    is_overdue: false,
    mock_interview_count: 0,
    interviews: [],
    mock_interviews: [],
    documents: [],
    notes: [],
    status_history: [
      {
        status: "learning",
        started_at: "2026-07-01T10:00:00Z",
        ended_at: null,
        days: 45,
      },
    ],
  };
  vi.spyOn(api, "mentorStudent").mockResolvedValue(student);

  renderPage(
    <MentorStudentPage />,
    "/mentor/students/student-1",
    "/mentor/students/:studentId",
  );

  const telegramLink = await screen.findByRole("link", {
    name: "Написать в Telegram · @ivan_detail",
  });
  expect(telegramLink).toHaveAttribute("href", "https://t.me/ivan_detail");
  expect(telegramLink).toHaveAttribute("target", "_blank");
  expect(telegramLink).toHaveAttribute("rel", "noopener noreferrer");
  expect(screen.getByText("История статусов")).toBeInTheDocument();
  expect(screen.getAllByText("45 дн.")).toHaveLength(2);
});

it.each([
  ["video/mp4", "Посмотреть запись", "video"],
  ["audio/mpeg", "Прослушать запись", "audio"],
])(
  "открывает защищённую запись ученика для фидбека: %s",
  async (contentType, buttonName, playerTag) => {
    const stageId = "71000000-0000-4000-8000-000000000001";
    const detail: MentorInterviewDetail = {
      process: {
        id: "70000000-0000-4000-8000-000000000001",
        company_name: "Яндекс",
        recruiter_telegram_usernames: [],
        track_id: "40000000-0000-4000-8000-000000000001",
        track_slug: "python",
        track_title: "Python",
        status: "active",
        close_reason: null,
        closed_at: null,
        stage_count: 1,
        next_stage_at: null,
        has_offer_file: false,
        created_at: "2026-08-01T10:00:00Z",
        updated_at: "2026-08-01T10:00:00Z",
        offer: null,
        stages: [
          {
            id: stageId,
            stage_type: "technical_interview",
            scheduled_at: "2026-08-05T12:00:00Z",
            description: "Алгоритмы и Python",
            media: {
              filename: contentType.startsWith("video/")
                ? "recording.mp4"
                : "recording.mp3",
              content_type: contentType,
              size: 0,
            },
            attachments: [],
            created_at: "2026-08-01T10:00:00Z",
            updated_at: "2026-08-01T10:00:00Z",
          },
        ],
      },
      feedback: [{ stage_id: stageId, comments: [] }],
    };
    vi.spyOn(api, "mentorInterview").mockResolvedValue(detail);
    const media = vi
      .spyOn(api, "interviewCatalogStageMedia")
      .mockResolvedValue(`https://platform.test/media/${stageId}/stream`);

    renderPage(
      <MentorInterviewPage />,
      `/mentor/students/student-1/interviews/${detail.process.id}`,
      "/mentor/students/:studentId/interviews/:processId",
    );
    await userEvent.click(
      await screen.findByRole("button", { name: buttonName }),
    );

    await waitFor(() => {
      const player = document.querySelector<HTMLMediaElement>(
        `${playerTag}[controls]`,
      );
      expect(player?.src).toContain(`/media/${stageId}/stream`);
      expect(player).toHaveAttribute("preload", "metadata");
    });
    expect(media).toHaveBeenCalledWith(stageId);
  },
);
