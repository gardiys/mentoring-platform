import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { MentorProfilePage } from "../src/pages/MentorProfilePage";
import type {
  MentorProfileRead,
  ScheduleEventRead,
  ScheduleTrackRead,
} from "../src/types/api";
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

function weeklyCall(
  overrides: Partial<ScheduleEventRead> = {},
): ScheduleEventRead {
  return {
    id: "50000000-0000-4000-8000-000000000001",
    track: pythonTrack,
    mentor_id: "10000000-0000-4000-8000-000000000001",
    source: "mentor",
    source_name: "Антон",
    kind: "weekly_call",
    title: "Python weekly",
    description: null,
    meeting_url: "https://meet.example.com/python-weekly",
    weekday: 1,
    starts_at_time: "19:00:00",
    timezone: "Europe/Moscow",
    starts_at: null,
    regular_next_occurrence_at: "2026-08-11T16:00:00Z",
    next_occurrence_at: "2026-08-11T16:00:00Z",
    is_rescheduled: false,
    rescheduled_from: null,
    rescheduled_to: null,
    created_at: "2026-08-04T10:00:00Z",
    updated_at: "2026-08-04T10:00:00Z",
    ...overrides,
  };
}

function oneOffActivity(
  overrides: Partial<ScheduleEventRead> = {},
): ScheduleEventRead {
  return weeklyCall({
    id: "50000000-0000-4000-8000-000000000002",
    kind: "meeting",
    title: "Мок-собеседование",
    meeting_url: null,
    weekday: null,
    starts_at_time: null,
    timezone: null,
    starts_at: "2035-08-15T16:30:00Z",
    regular_next_occurrence_at: null,
    next_occurrence_at: "2035-08-15T16:30:00Z",
    ...overrides,
  });
}

function mentorProfile(
  overrides: Partial<MentorProfileRead> = {},
): MentorProfileRead {
  return {
    mentor_id: "10000000-0000-4000-8000-000000000001",
    consultation_url: "https://calendar.example.com/old",
    group_calendar_url: "https://calendar.example.com/group-old",
    tracks: [pythonTrack, goTrack],
    weekly_calls: [],
    one_off_activities: [],
    updated_at: "2026-08-04T10:00:00Z",
    ...overrides,
  };
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

it("сохраняет ссылки на консультацию и общий календарь", async () => {
  vi.spyOn(api, "mentorProfile").mockResolvedValue(mentorProfile());
  const update = vi
    .spyOn(api, "updateMentorProfile")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<MentorProfilePage />, "/mentor/profile", "/mentor/profile");

  const input = await screen.findByLabelText("Ссылка для записи");
  await userEvent.clear(input);
  await userEvent.type(input, "https://calendar.example.com/anton");
  const groupCalendar = screen.getByLabelText(
    "Календарь общих созвонов группы",
  );
  await userEvent.clear(groupCalendar);
  await userEvent.type(
    groupCalendar,
    "https://calendar.example.com/anton/group",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить ссылки" }),
  );

  expect(update).toHaveBeenCalledWith({
    consultation_url: "https://calendar.example.com/anton",
    group_calendar_url: "https://calendar.example.com/anton/group",
  });
});

it("создаёт регулярный созвон с направлением, днём, временем и ссылкой", async () => {
  vi.spyOn(api, "mentorProfile").mockResolvedValue(mentorProfile());
  const create = vi
    .spyOn(api, "createMentorWeeklyCall")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<MentorProfilePage />, "/mentor/profile", "/mentor/profile");

  await userEvent.click(
    await screen.findByRole("button", { name: "+ Добавить событие" }),
  );
  const dialog = await screen.findByRole("dialog");

  await selectOption(
    within(dialog).getByRole("textbox", { name: "Направление" }),
    "Go",
  );
  const title = await screen.findByRole("textbox", { name: "Тема" });
  await userEvent.type(title, "Go: разбор недели");
  await selectOption(
    screen.getByRole("textbox", { name: "День недели" }),
    "Четверг",
  );
  await userEvent.type(screen.getByLabelText("Время"), "19:30");
  const meetingUrl = dialog.querySelector<HTMLInputElement>(
    'input[type="url"][placeholder="https://meet.google.com/..."]',
  );
  expect(meetingUrl).not.toBeNull();
  await userEvent.type(meetingUrl!, "https://meet.example.com/go-weekly");
  await userEvent.click(
    screen.getByRole("button", { name: "Добавить событие" }),
  );

  expect(create).toHaveBeenCalledWith({
    track_id: goTrack.id,
    title: "Go: разбор недели",
    description: null,
    weekday: 3,
    starts_at_time: "19:30",
    timezone: "Europe/Moscow",
    meeting_url: "https://meet.example.com/go-weekly",
  });
});

it("создаёт разовую активность с будущей датой по Москве и без ссылки", async () => {
  vi.spyOn(api, "mentorProfile").mockResolvedValue(mentorProfile());
  const create = vi
    .spyOn(api, "createMentorOneOffActivity")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<MentorProfilePage />, "/mentor/profile", "/mentor/profile");

  await userEvent.click(
    await screen.findByRole("button", { name: "+ Добавить событие" }),
  );
  const dialog = await screen.findByRole("dialog");
  await selectOption(
    within(dialog).getByRole("textbox", { name: "Тип" }),
    "Разовая встреча",
  );
  await selectOption(
    within(dialog).getByRole("textbox", { name: "Направление" }),
    "Go",
  );
  await userEvent.type(
    within(dialog).getByRole("textbox", { name: "Тема" }),
    "Go mock interview",
  );
  const startsAt = dialog.querySelector<HTMLInputElement>(
    'input[type="datetime-local"]',
  );
  expect(startsAt).not.toBeNull();
  await userEvent.type(startsAt!, "2035-08-15T19:30");
  await userEvent.type(
    within(dialog).getByRole("textbox", { name: "Описание" }),
    "Практика системного дизайна",
  );
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Добавить событие" }),
  );

  expect(create).toHaveBeenCalledWith({
    track_id: goTrack.id,
    title: "Go mock interview",
    description: "Практика системного дизайна",
    starts_at: "2035-08-15T19:30:00+03:00",
    meeting_url: null,
  });
});

it("не принимает прошедшую дату разовой активности", async () => {
  vi.spyOn(api, "mentorProfile").mockResolvedValue(mentorProfile());
  const create = vi
    .spyOn(api, "createMentorOneOffActivity")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<MentorProfilePage />, "/mentor/profile", "/mentor/profile");

  await userEvent.click(
    await screen.findByRole("button", { name: "+ Добавить событие" }),
  );
  const dialog = await screen.findByRole("dialog");
  await selectOption(
    within(dialog).getByRole("textbox", { name: "Тип" }),
    "Разовая встреча",
  );
  await userEvent.type(
    within(dialog).getByRole("textbox", { name: "Тема" }),
    "Встреча из прошлого",
  );
  const startsAt = dialog.querySelector<HTMLInputElement>(
    'input[type="datetime-local"]',
  );
  expect(startsAt).not.toBeNull();
  await userEvent.type(startsAt!, "2020-01-01T10:00");

  expect(
    within(dialog).getByText("Выберите будущую дату и время по Москве"),
  ).toBeInTheDocument();
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Добавить событие" }),
  );
  expect(create).not.toHaveBeenCalled();
});

it("редактирует разовую активность через отдельный endpoint", async () => {
  const activity = oneOffActivity();
  vi.spyOn(api, "mentorProfile").mockResolvedValue(
    mentorProfile({ one_off_activities: [activity] }),
  );
  const update = vi
    .spyOn(api, "updateMentorOneOffActivity")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<MentorProfilePage />, "/mentor/profile", "/mentor/profile");

  expect(await screen.findByText("Мок-собеседование")).toBeInTheDocument();
  expect(screen.getByText("Разовая")).toBeInTheDocument();
  expect(screen.getByText("Не указана")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Изменить" }));
  const dialog = await screen.findByRole("dialog");
  const title = within(dialog).getByRole("textbox", { name: "Тема" });
  await userEvent.clear(title);
  await userEvent.type(title, "Мок по алгоритмам");
  const startsAt = dialog.querySelector<HTMLInputElement>(
    'input[type="datetime-local"]',
  );
  expect(startsAt).not.toBeNull();
  await userEvent.clear(startsAt!);
  await userEvent.type(startsAt!, "2035-08-16T20:00");
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Сохранить" }),
  );

  expect(update).toHaveBeenCalledWith(activity.id, {
    track_id: pythonTrack.id,
    title: "Мок по алгоритмам",
    description: null,
    starts_at: "2035-08-16T20:00:00+03:00",
    meeting_url: null,
  });
});

it("переносит ближайший регулярный созвон по московскому времени", async () => {
  const event = weeklyCall({
    regular_next_occurrence_at: "2035-08-11T16:00:00Z",
    next_occurrence_at: "2035-08-11T16:00:00Z",
  });
  vi.spyOn(api, "mentorProfile").mockResolvedValue(
    mentorProfile({ weekly_calls: [event] }),
  );
  const reschedule = vi
    .spyOn(api, "rescheduleMentorWeeklyCall")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<MentorProfilePage />, "/mentor/profile", "/mentor/profile");

  await userEvent.click(
    await screen.findByRole("button", { name: "Перенести ближайший" }),
  );
  const dialog = await screen.findByRole("dialog");
  const startsAt = dialog.querySelector<HTMLInputElement>(
    'input[type="datetime-local"]',
  );
  expect(startsAt).not.toBeNull();
  await userEvent.clear(startsAt!);
  await userEvent.type(startsAt!, "2035-08-12T20:30");
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Сохранить перенос" }),
  );

  expect(reschedule).toHaveBeenCalledWith(event.id, {
    starts_at: "2035-08-12T20:30:00+03:00",
  });
});

it("не предлагает перенос, пока у регулярного созвона не задано время", async () => {
  const event = weeklyCall({
    starts_at_time: null,
    regular_next_occurrence_at: null,
    next_occurrence_at: null,
  });
  vi.spyOn(api, "mentorProfile").mockResolvedValue(
    mentorProfile({ weekly_calls: [event] }),
  );
  renderPage(<MentorProfilePage />, "/mentor/profile", "/mentor/profile");

  const button = await screen.findByRole("button", {
    name: "Перенести ближайший",
  });
  expect(button).toBeDisabled();
  expect(button).toHaveAttribute(
    "title",
    "Сначала укажите время регулярного созвона",
  );
});

it("показывает пометку переноса и позволяет отменить будущий перенос", async () => {
  const event = weeklyCall({
    regular_next_occurrence_at: "2035-08-11T16:00:00Z",
    next_occurrence_at: "2035-08-12T17:30:00Z",
    is_rescheduled: true,
    rescheduled_from: "2035-08-11T16:00:00Z",
    rescheduled_to: "2035-08-12T17:30:00Z",
  });
  vi.spyOn(api, "mentorProfile").mockResolvedValue(
    mentorProfile({ weekly_calls: [event] }),
  );
  const cancel = vi
    .spyOn(api, "cancelMentorWeeklyCallReschedule")
    .mockReturnValue(new Promise(() => undefined));
  vi.spyOn(window, "confirm").mockReturnValue(true);
  renderPage(<MentorProfilePage />, "/mentor/profile", "/mentor/profile");

  expect(await screen.findByText("Ближайший перенесён")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Отменить перенос" }),
  );

  expect(window.confirm).toHaveBeenCalledWith(
    `Отменить перенос созвона «${event.title}»?`,
  );
  expect(cancel.mock.calls[0]?.[0]).toBe(event.id);
});

it("удаляет разовую активность через её endpoint", async () => {
  const activity = oneOffActivity();
  vi.spyOn(api, "mentorProfile").mockResolvedValue(
    mentorProfile({ one_off_activities: [activity] }),
  );
  const remove = vi
    .spyOn(api, "deleteMentorOneOffActivity")
    .mockReturnValue(new Promise(() => undefined));
  vi.spyOn(window, "confirm").mockReturnValue(true);
  renderPage(<MentorProfilePage />, "/mentor/profile", "/mentor/profile");

  await userEvent.click(await screen.findByRole("button", { name: "Удалить" }));

  expect(window.confirm).toHaveBeenCalledWith(
    `Удалить разовую встречу «${activity.title}»?`,
  );
  expect(remove.mock.calls[0]?.[0]).toBe(activity.id);
});

it("удаляет регулярный созвон только после подтверждения", async () => {
  const event = weeklyCall();
  vi.spyOn(api, "mentorProfile").mockResolvedValue(
    mentorProfile({ weekly_calls: [event] }),
  );
  const remove = vi
    .spyOn(api, "deleteMentorWeeklyCall")
    .mockReturnValue(new Promise(() => undefined));
  vi.spyOn(window, "confirm").mockReturnValue(true);
  renderPage(<MentorProfilePage />, "/mentor/profile", "/mentor/profile");

  await userEvent.click(await screen.findByRole("button", { name: "Удалить" }));

  expect(window.confirm).toHaveBeenCalledWith(
    `Удалить созвон «${event.title}»?`,
  );
  expect(remove.mock.calls[0]?.[0]).toBe(event.id);
});
