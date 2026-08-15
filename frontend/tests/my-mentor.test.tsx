import { screen, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { MyMentorPage } from "../src/pages/MyMentorPage";
import type {
  MyMentorDashboardRead,
  ScheduleEventRead,
  ScheduleTrackRead,
} from "../src/types/api";
import { formatMoscowDateTime } from "../src/utils/schedule";
import { renderPage } from "./render";

const pythonTrack: ScheduleTrackRead = {
  id: "40000000-0000-4000-8000-000000000001",
  slug: "python",
  title: "Python",
};

const goTrack: ScheduleTrackRead = {
  id: "40000000-0000-4000-8000-000000000002",
  slug: "go",
  title: "Go",
};

function scheduleEvent(
  overrides: Partial<ScheduleEventRead> = {},
): ScheduleEventRead {
  return {
    id: "50000000-0000-4000-8000-000000000001",
    track: pythonTrack,
    mentor_id: null,
    source: "platform",
    source_name: "Платформа",
    kind: "meeting",
    title: "Общая встреча Python",
    description: "Разберём вопросы по обучению",
    meeting_url: "https://meet.example.com/python-all",
    weekday: null,
    starts_at_time: null,
    timezone: null,
    starts_at: "2026-08-15T16:00:00Z",
    regular_next_occurrence_at: null,
    next_occurrence_at: "2026-08-15T16:00:00Z",
    is_rescheduled: false,
    rescheduled_from: null,
    rescheduled_to: null,
    created_at: "2026-08-04T10:00:00Z",
    updated_at: "2026-08-04T10:00:00Z",
    ...overrides,
  };
}

afterEach(() => vi.restoreAllMocks());

it("показывает контакты ментора, консультацию и оба источника расписания", async () => {
  const mentorCall = scheduleEvent({
    id: "50000000-0000-4000-8000-000000000002",
    mentor_id: "10000000-0000-4000-8000-000000000001",
    source: "mentor",
    source_name: "Антон Менторов",
    kind: "weekly_call",
    title: "Созвон с ментором",
    description: null,
    meeting_url: "https://meet.example.com/mentor-python",
    weekday: 1,
    starts_at_time: "19:30:00",
    timezone: "Europe/Moscow",
    starts_at: null,
    regular_next_occurrence_at: "2026-08-11T16:30:00Z",
    next_occurrence_at: "2026-08-12T17:00:00Z",
    is_rescheduled: true,
    rescheduled_from: "2026-08-11T16:30:00Z",
    rescheduled_to: "2026-08-12T17:00:00Z",
  });
  const dashboard: MyMentorDashboardRead = {
    mentor: {
      id: "10000000-0000-4000-8000-000000000001",
      first_name: "Антон",
      last_name: "Менторов",
      telegram_username: "codewaste_mentor",
      consultation_url: "https://calendar.example.com/anton",
      group_calendars: [
        {
          track: pythonTrack,
          calendar_url: "https://calendar.example.com/anton/python",
        },
        {
          track: goTrack,
          calendar_url: "https://calendar.example.com/anton/go",
        },
      ],
    },
    schedule: [mentorCall, scheduleEvent()],
    useful_links: [
      {
        id: "60000000-0000-4000-8000-000000000001",
        title: "Чат сообщества",
        description: "Общие вопросы и новости",
        url: "https://t.me/example-community",
        position: 0,
        created_at: "2026-08-04T10:00:00Z",
        updated_at: "2026-08-04T10:00:00Z",
      },
    ],
  };
  vi.spyOn(api, "myMentorDashboard").mockResolvedValue(dashboard);

  renderPage(<MyMentorPage />, "/my-mentor", "/my-mentor");

  expect(
    await screen.findByRole("heading", { name: "Антон Менторов" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "@codewaste_mentor" }),
  ).toHaveAttribute("href", "https://t.me/codewaste_mentor");
  const telegramButton = screen.getByRole("link", {
    name: "Написать в Telegram",
  });
  expect(telegramButton).toHaveAttribute(
    "href",
    "https://t.me/codewaste_mentor",
  );
  expect(telegramButton).toHaveAttribute("target", "_blank");
  expect(telegramButton).toHaveAttribute("rel", "noopener noreferrer");
  expect(
    screen.getByRole("link", { name: "Записаться на консультацию" }),
  ).toHaveAttribute("href", "https://calendar.example.com/anton");
  expect(
    screen.getByRole("link", { name: "Календарь Python" }),
  ).toHaveAttribute("href", "https://calendar.example.com/anton/python");
  expect(screen.getByRole("link", { name: "Календарь Go" })).toHaveAttribute(
    "href",
    "https://calendar.example.com/anton/go",
  );
  expect(screen.getByText("Чат сообщества")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Открыть ссылку" })).toHaveAttribute(
    "href",
    "https://t.me/example-community",
  );

  expect(screen.getByText("Созвон с ментором")).toBeInTheDocument();
  expect(screen.getByText("Общая встреча Python")).toBeInTheDocument();
  expect(screen.getByText("Ментор: Антон Менторов")).toBeInTheDocument();
  expect(screen.getByText("Событие направления")).toBeInTheDocument();
  const rescheduledCard = screen.getByRole("article", {
    name: "Созвон с ментором — созвон перенесён",
  });
  const rescheduleNotice = within(rescheduledCard).getByRole("status", {
    name: "Созвон перенесён",
  });
  expect(
    within(rescheduledCard).getByText(/Обычное расписание:/),
  ).toBeInTheDocument();
  expect(
    within(rescheduleNotice).getByText("Новая дата и время"),
  ).toBeInTheDocument();
  const newDate = rescheduleNotice.querySelector("time");
  expect(newDate).toHaveAttribute("datetime", "2026-08-12T17:00:00Z");
  expect(newDate).toHaveTextContent(
    formatMoscowDateTime("2026-08-12T17:00:00Z"),
  );
  const oldDate = rescheduleNotice.querySelector("del");
  expect(oldDate).toHaveTextContent(
    formatMoscowDateTime("2026-08-11T16:30:00Z"),
  );
  expect(
    within(rescheduleNotice).getByText("Время указано по Москве"),
  ).toBeInTheDocument();

  const eventLinks = screen.getAllByRole("link", {
    name: "Подключиться к встрече",
  });
  expect(eventLinks).toHaveLength(2);
  expect(eventLinks.map((link) => link.getAttribute("href"))).toEqual([
    "https://meet.example.com/mentor-python",
    "https://meet.example.com/python-all",
  ]);
});

it("показывает общие события направления даже без назначенного ментора", async () => {
  const globalEvent = scheduleEvent();
  vi.spyOn(api, "myMentorDashboard").mockResolvedValue({
    mentor: null,
    schedule: [globalEvent],
    useful_links: [],
  });

  renderPage(<MyMentorPage />, "/my-mentor", "/my-mentor");

  expect(await screen.findByText("Ментор ещё не назначен")).toBeInTheDocument();
  expect(screen.getByText(globalEvent.title)).toBeInTheDocument();
  expect(screen.getByText("Событие направления")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Подключиться к встрече" }),
  ).toHaveAttribute("href", globalEvent.meeting_url);
  expect(
    screen.queryByRole("link", { name: "Записаться на консультацию" }),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Написать в Telegram" }),
  ).not.toBeInTheDocument();
});

it("не показывает кнопку Telegram, если у ментора нет username", async () => {
  vi.spyOn(api, "myMentorDashboard").mockResolvedValue({
    mentor: {
      id: "10000000-0000-4000-8000-000000000001",
      first_name: "Антон",
      last_name: "Менторов",
      telegram_username: null,
      consultation_url: null,
      group_calendars: [],
    },
    schedule: [],
    useful_links: [],
  });

  renderPage(<MyMentorPage />, "/my-mentor", "/my-mentor");

  expect(
    await screen.findByRole("heading", { name: "Антон Менторов" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("link", { name: "Написать в Telegram" }),
  ).not.toBeInTheDocument();
});
