import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminSchedulePage } from "../src/pages/AdminSchedulePage";
import type {
  AdminTrackRead,
  ScheduleEventRead,
  ScheduleTrackRead,
} from "../src/types/api";
import { renderPage } from "./render";

const pythonScheduleTrack: ScheduleTrackRead = {
  id: "40000000-0000-4000-8000-000000000001",
  slug: "python",
  title: "Python",
};

const goScheduleTrack: ScheduleTrackRead = {
  id: "40000000-0000-4000-8000-000000000002",
  slug: "go",
  title: "Go",
};

const adminTracks: AdminTrackRead[] = [
  {
    ...pythonScheduleTrack,
    description: null,
    position: 0,
    is_published: true,
    roadmaps: [],
    student_ids: [],
  },
  {
    ...goScheduleTrack,
    description: null,
    position: 1,
    is_published: true,
    roadmaps: [],
    student_ids: [],
  },
];

function scheduleEvent(
  overrides: Partial<ScheduleEventRead> = {},
): ScheduleEventRead {
  return {
    id: "50000000-0000-4000-8000-000000000001",
    track: pythonScheduleTrack,
    mentor_id: null,
    source: "platform",
    source_name: "Платформа",
    kind: "weekly_call",
    title: "Python weekly",
    description: null,
    meeting_url: "https://meet.example.com/python-weekly",
    weekday: 0,
    starts_at_time: "19:00:00",
    timezone: "Europe/Moscow",
    starts_at: null,
    regular_next_occurrence_at: "2026-08-10T16:00:00Z",
    next_occurrence_at: "2026-08-10T16:00:00Z",
    is_rescheduled: false,
    rescheduled_from: null,
    rescheduled_to: null,
    created_at: "2026-08-04T10:00:00Z",
    updated_at: "2026-08-04T10:00:00Z",
    ...overrides,
  };
}

function mockSchedulePage(total = 0, items: ScheduleEventRead[] = []) {
  return vi.spyOn(api, "adminScheduleEvents").mockResolvedValue({
    items,
    total,
    limit: 20,
    offset: 0,
  });
}

async function selectOption(input: HTMLElement, label: string) {
  await userEvent.click(input);
  await waitFor(() => expect(input).toHaveAttribute("aria-controls"));
  const listboxId = input.getAttribute("aria-controls");
  expect(listboxId).not.toBeNull();
  const listbox = document.getElementById(listboxId!);
  expect(listbox).not.toBeNull();
  await userEvent.click(within(listbox!).getByText(label));
}

afterEach(() => vi.restoreAllMocks());

it("фильтрует события и переключает страницу", async () => {
  vi.spyOn(api, "adminTracks").mockResolvedValue(adminTracks);
  const list = mockSchedulePage(21, [scheduleEvent()]);
  renderPage(<AdminSchedulePage />, "/admin/schedule", "/admin/schedule");

  expect(await screen.findByText("Python weekly")).toBeInTheDocument();
  await selectOption(
    screen.getByRole("textbox", { name: "Направление" }),
    "Go",
  );
  await waitFor(() =>
    expect(list).toHaveBeenLastCalledWith({
      trackId: goScheduleTrack.id,
      kind: null,
      limit: 20,
      offset: 0,
    }),
  );

  await selectOption(
    screen.getByRole("textbox", { name: "Тип события" }),
    "Регулярный созвон",
  );
  await waitFor(() =>
    expect(list).toHaveBeenLastCalledWith({
      trackId: goScheduleTrack.id,
      kind: "weekly_call",
      limit: 20,
      offset: 0,
    }),
  );

  await userEvent.click(screen.getByRole("button", { name: "2" }));
  await waitFor(() =>
    expect(list).toHaveBeenLastCalledWith({
      trackId: goScheduleTrack.id,
      kind: "weekly_call",
      limit: 20,
      offset: 20,
    }),
  );
});

it("создаёт регулярное событие направления", async () => {
  vi.spyOn(api, "adminTracks").mockResolvedValue(adminTracks);
  mockSchedulePage();
  const create = vi
    .spyOn(api, "createAdminScheduleEvent")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<AdminSchedulePage />, "/admin/schedule", "/admin/schedule");

  await userEvent.click(
    await screen.findByRole("button", { name: "+ Добавить событие" }),
  );
  const dialog = await screen.findByRole("dialog");
  await selectOption(
    within(dialog).getByRole("textbox", { name: "Направление" }),
    "Go",
  );
  const title = await screen.findByRole("textbox", { name: "Название" });
  await userEvent.clear(title);
  await userEvent.type(title, "Go общий созвон");
  await selectOption(
    screen.getByRole("textbox", { name: "День недели" }),
    "Вторник",
  );
  await userEvent.type(screen.getByLabelText("Время"), "18:30");
  const meetingUrl = dialog.querySelector<HTMLInputElement>(
    'input[type="url"][placeholder="https://meet.google.com/..."]',
  );
  expect(meetingUrl).not.toBeNull();
  await userEvent.type(meetingUrl!, "https://meet.example.com/go-all");
  await userEvent.click(
    screen.getByRole("button", { name: "Добавить событие" }),
  );

  expect(create).toHaveBeenCalledWith({
    track_id: goScheduleTrack.id,
    kind: "weekly_call",
    title: "Go общий созвон",
    description: null,
    meeting_url: "https://meet.example.com/go-all",
    weekday: 1,
    starts_at_time: "18:30",
    timezone: "Europe/Moscow",
    starts_at: null,
  });
});

it("сериализует разовую встречу с явным московским смещением", async () => {
  vi.spyOn(api, "adminTracks").mockResolvedValue(adminTracks);
  mockSchedulePage();
  const create = vi
    .spyOn(api, "createAdminScheduleEvent")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<AdminSchedulePage />, "/admin/schedule", "/admin/schedule");

  await userEvent.click(
    await screen.findByRole("button", { name: "+ Добавить событие" }),
  );
  const dialog = await screen.findByRole("dialog");
  await selectOption(
    within(dialog).getByRole("textbox", { name: "Тип события" }),
    "Разовая встреча",
  );
  const title = await screen.findByRole("textbox", { name: "Название" });
  await userEvent.clear(title);
  await userEvent.type(title, "Разбор резюме Python");
  const startsAt = dialog.querySelector<HTMLInputElement>(
    'input[type="datetime-local"]',
  );
  expect(startsAt).not.toBeNull();
  await userEvent.type(startsAt!, "2026-08-15T19:30");
  const meetingUrl = dialog.querySelector<HTMLInputElement>(
    'input[type="url"][placeholder="https://meet.google.com/..."]',
  );
  expect(meetingUrl).not.toBeNull();
  await userEvent.type(meetingUrl!, "https://meet.example.com/resume-review");
  await userEvent.click(
    screen.getByRole("button", { name: "Добавить событие" }),
  );

  expect(create).toHaveBeenCalledWith({
    track_id: pythonScheduleTrack.id,
    kind: "meeting",
    title: "Разбор резюме Python",
    description: null,
    meeting_url: "https://meet.example.com/resume-review",
    weekday: null,
    starts_at_time: null,
    timezone: null,
    starts_at: "2026-08-15T19:30:00+03:00",
  });
});

it("удаляет событие только после подтверждения", async () => {
  const event = scheduleEvent();
  vi.spyOn(api, "adminTracks").mockResolvedValue(adminTracks);
  mockSchedulePage(1, [event]);
  const remove = vi
    .spyOn(api, "deleteAdminScheduleEvent")
    .mockReturnValue(new Promise(() => undefined));
  vi.spyOn(window, "confirm").mockReturnValue(true);
  renderPage(<AdminSchedulePage />, "/admin/schedule", "/admin/schedule");

  await userEvent.click(await screen.findByRole("button", { name: "Удалить" }));

  expect(window.confirm).toHaveBeenCalledWith(
    `Удалить событие «${event.title}»?`,
  );
  expect(remove.mock.calls[0]?.[0]).toBe(event.id);
});
