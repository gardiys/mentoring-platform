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
  expect(screen.getByText(/Завершите оплату в боте/)).toBeInTheDocument();
});
