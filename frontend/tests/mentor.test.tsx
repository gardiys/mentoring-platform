import { screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { MentorStudentsPage } from "../src/pages/MentorStudentsPage";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

it("MentorStudentsPage отображает учеников", async () => {
  vi.spyOn(api, "mentorStudents").mockResolvedValue([
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
  ]);
  renderPage(<MentorStudentsPage />);
  expect(await screen.findByText("Иван Иванов")).toBeInTheDocument();
});
