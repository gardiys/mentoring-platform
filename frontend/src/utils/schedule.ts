import type { ScheduleEventRead } from "../types/api";

export const WEEKDAYS = [
  "Понедельник",
  "Вторник",
  "Среда",
  "Четверг",
  "Пятница",
  "Суббота",
  "Воскресенье",
] as const;

export const WEEKDAY_OPTIONS = WEEKDAYS.map((label, value) => ({
  value: String(value),
  label,
}));

export const TIMEZONE_OPTIONS = [
  { value: "Europe/Moscow", label: "Москва (UTC+3)" },
  { value: "Europe/Kaliningrad", label: "Калининград (UTC+2)" },
  { value: "Asia/Yekaterinburg", label: "Екатеринбург (UTC+5)" },
  { value: "Asia/Novosibirsk", label: "Новосибирск (UTC+7)" },
  { value: "Asia/Vladivostok", label: "Владивосток (UTC+10)" },
] as const;

export function weekdayName(weekday: number | null): string {
  return weekday === null
    ? "День не указан"
    : (WEEKDAYS[weekday] ?? "День не указан");
}

export function shortTime(value: string | null): string | null {
  return value ? value.slice(0, 5) : null;
}

export function scheduleTimezoneLabel(timezone: string | null): string {
  if (!timezone) return "";
  return (
    TIMEZONE_OPTIONS.find((option) => option.value === timezone)?.label ??
    timezone
  );
}

export function formatMoscowDateTime(value: string): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "long",
    timeStyle: "short",
    timeZone: "Europe/Moscow",
  }).format(new Date(value));
}

export function moscowInputToIso(value: string): string {
  return `${value}:00+03:00`;
}

export function isoToMoscowInput(value: string | null): string {
  if (!value) return "";
  const parts = new Intl.DateTimeFormat("en-CA", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone: "Europe/Moscow",
  }).formatToParts(new Date(value));
  const part = (type: Intl.DateTimeFormatPartTypes) =>
    parts.find((item) => item.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}-${part("day")}T${part("hour")}:${part("minute")}`;
}

export function scheduleEventTiming(event: ScheduleEventRead): string {
  if (event.kind === "meeting" && event.starts_at) {
    return formatMoscowDateTime(event.starts_at);
  }
  const time = shortTime(event.starts_at_time);
  const timezone = scheduleTimezoneLabel(event.timezone);
  return [weekdayName(event.weekday), time, timezone]
    .filter(Boolean)
    .join(" · ");
}
