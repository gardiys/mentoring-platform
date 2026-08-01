import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { MentorStudentsPage } from "../src/pages/MentorStudentsPage";
import { MentorInterviewPage } from "../src/pages/MentorInterviewPage";
import type { MentorInterviewDetail } from "../src/types/api";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

it("MentorStudentsPage отображает учеников", async () => {
  vi.spyOn(api, "mentorStudents").mockResolvedValue({
    items: [
      {
        id: "u1",
        first_name: "Иван",
        last_name: "Иванов",
        email: "student@example.com",
        telegram_username: null,
        learning_status: "learning",
        strength_level: null,
        roadmaps: [],
        current_topics: [],
        last_progress_at: null,
        completed_topics_this_week: 0,
        is_overdue: false,
        mock_interview_count: 0,
      },
    ],
    total: 1,
    limit: 12,
    offset: 0,
    directions: [{ id: "python", slug: "python", title: "Python" }],
    mentors: [
      {
        id: "mentor-1",
        first_name: "Антон",
        last_name: "Менторов",
        telegram_username: "mentor",
      },
    ],
    can_filter_by_mentor: true,
  });
  renderPage(<MentorStudentsPage />);
  expect(await screen.findByText("Иван Иванов")).toBeInTheDocument();
  expect(screen.getAllByLabelText("Направление")[0]).toBeInTheDocument();
  expect(screen.getAllByLabelText("Текущий статус")[0]).toBeInTheDocument();
  expect(screen.getAllByLabelText("Ментор")[0]).toBeInTheDocument();
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
    });
    expect(media).toHaveBeenCalledWith(stageId);
  },
);
