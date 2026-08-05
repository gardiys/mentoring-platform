import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { MentorInterviewIntelligencePage } from "../src/pages/MentorInterviewIntelligencePage";
import type {
  AdminIntelligenceOperations,
  IntelligenceInterviewSummary,
  User,
} from "../src/types/api";
import { renderPage } from "./render";

const admin: User = {
  id: "90000000-0000-4000-8000-000000000001",
  telegram_id: 123456789,
  first_name: "Администратор",
  last_name: null,
  email: null,
  role: "admin",
  onboarding_completed_at: "2026-08-01T00:00:00Z",
  is_active: true,
};

const mentor: User = {
  ...admin,
  id: "80000000-0000-4000-8000-000000000001",
  first_name: "Ментор",
  role: "mentor",
};

const requestedInterview: IntelligenceInterviewSummary = {
  id: "70000000-0000-4000-8000-000000000001",
  stage_id: "71000000-0000-4000-8000-000000000001",
  process_id: "72000000-0000-4000-8000-000000000001",
  student_id: "20000000-0000-4000-8000-000000000001",
  student_name: "Иван",
  company_name: "Яндекс",
  position_name: "Python developer",
  track_id: "40000000-0000-4000-8000-000000000001",
  track_slug: "python",
  track_title: "Python",
  interview_type: "technical",
  interviewed_at: "2026-08-04T12:00:00Z",
  processing_status: "uploaded",
  failed_stage: null,
  processing_error_code: null,
  processing_error_message: null,
  can_requeue_processing: true,
  duration_ms: null,
  question_count: 0,
  suggested_review_count: 0,
  reviewed_count: 0,
  reviewed_at: null,
  reviewed_by_user_id: null,
  created_at: "2026-08-05T09:00:00Z",
  updated_at: "2026-08-05T09:00:00Z",
};

const operations: AdminIntelligenceOperations = {
  generated_at: "2026-08-05T09:05:00Z",
  total: 1,
  by_status: {
    draft: 0,
    uploaded: 1,
    transcription_submitted: 0,
    transcribing: 0,
    transcript_ready: 0,
    awaiting_candidate_speaker: 0,
    analyzing: 0,
    ready: 0,
    failed: 0,
  },
  active: 1,
  failed: 0,
  ready: 0,
  oldest_active_at: "2026-08-05T09:00:00Z",
  oldest_active_age_seconds: 300,
  launches_today: 1,
  failure_codes_24h: [],
  queues: {
    available: true,
    transcription_depth: 1,
    openai_depth: 0,
  },
  workers: {
    transcription: {
      status: "healthy",
      heartbeat: "ok",
      heartbeat_ttl_seconds: 30,
    },
    openai: {
      status: "healthy",
      heartbeat: "ok",
      heartbeat_ttl_seconds: 30,
    },
  },
};

afterEach(() => vi.restoreAllMocks());

it("даёт админу запустить ожидающий AI-разбор из очереди", async () => {
  vi.spyOn(api, "me").mockResolvedValue(admin);
  const list = vi.spyOn(api, "mentorIntelligenceInterviews").mockResolvedValue({
    items: [requestedInterview],
    total: 1,
    limit: 10,
    offset: 0,
  });
  vi.spyOn(api, "adminIntelligenceOperations").mockResolvedValue(operations);
  const requeue = vi
    .spyOn(api, "adminRequeueIntelligenceInterview")
    .mockResolvedValue({} as never);
  vi.spyOn(window, "confirm").mockReturnValue(true);

  renderPage(
    <MentorInterviewIntelligencePage />,
    "/mentor/interview-reviews",
    "/mentor/interview-reviews",
  );

  expect(
    await screen.findByRole("button", { name: "Запустить AI-разбор" }),
  ).toBeInTheDocument();
  expect(list).toHaveBeenCalledWith("requested", { limit: 10, offset: 0 });
  expect(list).toHaveBeenCalledTimes(1);

  await userEvent.click(
    screen.getByRole("button", { name: "Запустить AI-разбор" }),
  );

  expect(requeue).toHaveBeenCalledWith(requestedInterview.id);
});

it("показывает в списке безопасную причину ошибки", async () => {
  vi.spyOn(api, "me").mockResolvedValue(admin);
  vi.spyOn(api, "mentorIntelligenceInterviews").mockResolvedValue({
    items: [
      {
        ...requestedInterview,
        processing_status: "failed",
        failed_stage: "transcription_submit",
        processing_error_code: "INVALID_MEDIA_FILE",
        processing_error_message:
          "Файл не является корректной аудио- или видеозаписью.",
        can_requeue_processing: false,
      },
    ],
    total: 1,
    limit: 10,
    offset: 0,
  });
  vi.spyOn(api, "adminIntelligenceOperations").mockResolvedValue(operations);

  renderPage(
    <MentorInterviewIntelligencePage />,
    "/mentor/interview-reviews",
    "/mentor/interview-reviews",
  );

  expect(await screen.findByText("Причина остановки")).toBeInTheDocument();
  expect(
    screen.getByText("Файл не является корректной аудио- или видеозаписью."),
  ).toBeInTheDocument();
  expect(screen.getByText("Код: INVALID_MEDIA_FILE")).toBeInTheDocument();
});

it("не показывает ментору административный запуск", async () => {
  vi.spyOn(api, "me").mockResolvedValue(mentor);
  const list = vi.spyOn(api, "mentorIntelligenceInterviews").mockResolvedValue({
    items: [requestedInterview],
    total: 1,
    limit: 10,
    offset: 0,
  });
  const operationsRequest = vi.spyOn(api, "adminIntelligenceOperations");

  renderPage(
    <MentorInterviewIntelligencePage />,
    "/mentor/interview-reviews",
    "/mentor/interview-reviews",
  );

  expect(await screen.findByText("Яндекс")).toBeInTheDocument();
  expect(list).toHaveBeenCalledWith("needs_review", { limit: 10, offset: 0 });
  expect(
    screen.queryByRole("button", { name: "Запустить AI-разбор" }),
  ).not.toBeInTheDocument();
  expect(operationsRequest).not.toHaveBeenCalled();
});
