import userEvent from "@testing-library/user-event";
import { screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ApiError } from "../src/api/client";
import { api } from "../src/api/endpoints";
import { TelegramRequiredPage } from "../src/pages/TelegramRequiredPage";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

it("показывает браузерный Telegram-вход и сохраняет целевой маршрут", async () => {
  vi.spyOn(api, "me").mockRejectedValue(
    new ApiError(401, "unauthorized", "Unauthorized"),
  );

  renderPage(
    <TelegramRequiredPage />,
    "/login?next=/knowledge/topics/python",
    "/login",
  );

  const login = await screen.findByRole("link", {
    name: "Войти через Telegram",
  });
  expect(login).toHaveAttribute(
    "href",
    "http://localhost:8000/api/v1/auth/web/telegram/start?next=%2Fknowledge%2Ftopics%2Fpython",
  );
  expect(
    screen.getByText(/Новая регистрация на сайте не создаётся/),
  ).toBeInTheDocument();
});

it("объясняет, что бот ещё не выдал доступ", async () => {
  vi.spyOn(api, "me").mockRejectedValue(
    new ApiError(401, "unauthorized", "Unauthorized"),
  );

  renderPage(
    <TelegramRequiredPage />,
    "/login?error=platform_access_not_granted",
    "/login",
  );

  expect(await screen.findByText("Не удалось войти")).toBeInTheDocument();
  expect(screen.getByText(/Заверши оплату в боте/)).toBeInTheDocument();
});

it("отправляет форму локального входа по Enter", async () => {
  const { DevLoginPage } = await import("../src/pages/DevLoginPage");
  const { getDevUserId, clearDevUserId } =
    await import("../src/features/auth/devAuth");
  const user = userEvent.setup();
  clearDevUserId();
  try {
    const page = renderPage(<DevLoginPage />, "/dev-login", "/dev-login");
    const id = "20000000-0000-4000-8000-000000000001";
    await user.type(
      screen.getByRole("textbox", { name: "UUID пользователя" }),
      `${id}{Enter}`,
    );
    expect(getDevUserId()).toBe(id);
    expect(page.router.state.location.pathname).toBe("/roadmaps");
  } finally {
    clearDevUserId();
  }
});

it("объясняет ошибку UUID после отправки и оставляет возможность исправить ввод", async () => {
  const { DevLoginPage } = await import("../src/pages/DevLoginPage");
  const { getDevUserId, clearDevUserId } =
    await import("../src/features/auth/devAuth");
  clearDevUserId();
  const page = renderPage(<DevLoginPage />, "/dev-login", "/dev-login");
  const submit = screen.getByRole("button", { name: "Войти" });
  expect(submit).toBeEnabled();
  await userEvent.click(submit);
  expect(screen.getByText("Введи корректный UUID")).toBeInTheDocument();
  expect(page.router.state.location.pathname).toBe("/dev-login");
  expect(getDevUserId()).toBeNull();
});
