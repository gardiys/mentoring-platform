import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AppLayout } from "../src/components/AppLayout";
import { copilotApi } from "../src/features/copilot/api";
import { renderPage } from "./render";

beforeEach(() => {
  vi.spyOn(api, "me").mockResolvedValue({
    id: "90000000-0000-4000-8000-000000000001",
    first_name: "Администратор",
    last_name: null,
    email: null,
    telegram_id: 123,
    role: "admin",
    onboarding_completed_at: "2026-09-01T00:00:00Z",
    is_active: true,
  });
  vi.spyOn(api, "notifications").mockResolvedValue({
    items: [],
    total: 0,
    unread_count: 0,
    limit: 20,
    offset: 0,
  });
  vi.spyOn(copilotApi, "access").mockResolvedValue({
    allowed: true,
    student_allowed: false,
    students_enabled: true,
    learning_status: "studying",
    reason: "",
  });
});
afterEach(() => vi.restoreAllMocks());

it("оставляет один пункт модерации у администратора и одну область основного содержимого", async () => {
  renderPage(<AppLayout />, "/roadmaps", "/roadmaps", <h1>Роадмапы</h1>);
  await userEvent.click(
    await screen.findByRole("button", { name: "Модерация" }),
  );
  expect(
    await screen.findAllByRole("link", { name: /Модерация.*карточек/ }),
  ).toHaveLength(1);
  expect(screen.getAllByRole("main")).toHaveLength(1);
  expect(screen.queryByText("Геральт рядом")).not.toBeInTheDocument();
});

it("закрывает мобильное меню по Escape и возвращает фокус на кнопку открытия", async () => {
  vi.spyOn(window, "matchMedia").mockImplementation((query) => ({
    matches: query === "(max-width: 47.99em)",
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: () => false,
  }));
  renderPage(<AppLayout />, "/roadmaps", "/roadmaps", <h1>Роадмапы</h1>);
  const nav = screen.getByRole("navigation", { name: "Основная навигация" });
  await waitFor(() => expect(nav).toHaveAttribute("inert"));
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Открыть меню" }));
  expect(nav).not.toHaveAttribute("inert");
  expect(screen.getByRole("main")).toHaveAttribute("inert");
  screen.getByRole("link", { name: /База знаний/ }).focus();
  await user.keyboard("{Escape}");
  expect(nav).toHaveAttribute("inert");
  expect(screen.getByRole("main")).not.toHaveAttribute("inert");
  expect(screen.getByRole("button", { name: "Открыть меню" })).toHaveFocus();
});

it("показывает ученику семь разделов собеседований и выделяет только текущий", async () => {
  vi.mocked(api.me).mockResolvedValue({
    id: "20000000-0000-4000-8000-000000000001",
    first_name: "Ученик",
    last_name: null,
    email: null,
    telegram_id: 123,
    role: "student",
    onboarding_completed_at: "2026-09-01T00:00:00Z",
    is_active: true,
  });
  const { container } = renderPage(
    <AppLayout />,
    "/interviews/materials",
    "/interviews/materials",
    <h1>Материалы</h1>,
  );
  await screen.findByRole("link", { name: "Резюме и легенда" });
  for (const label of [
    "Вопросы с собеседований",
    "AI-разборы собеседований",
    "Дневник собеседований",
    "Мок-собеседования",
    "Резюме и легенда",
    "Каталог записей",
    "База рекрутеров",
  ]) {
    expect(
      screen.getByRole("link", { name: new RegExp(label) }),
    ).toBeInTheDocument();
  }
  const selected = container.querySelectorAll("nav a[data-active]");
  expect(selected).toHaveLength(1);
  expect(selected[0]).toHaveTextContent("Резюме и легенда");
});
