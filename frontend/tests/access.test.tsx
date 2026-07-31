import { screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ApiError } from "../src/api/client";
import { api } from "../src/api/endpoints";
import { ProtectedLayout } from "../src/components/ProtectedLayout";
import { renderPage } from "./render";

afterEach(() => {
  delete window.Telegram;
  vi.restoreAllMocks();
});

it("объясняет Telegram-пользователю, что доступ откроется после оплаты", async () => {
  window.Telegram = {
    WebApp: {
      initData: "query_id=test",
      colorScheme: "light",
      BackButton: {
        show: vi.fn(),
        hide: vi.fn(),
        onClick: vi.fn(),
        offClick: vi.fn(),
      },
      ready: vi.fn(),
      expand: vi.fn(),
      onEvent: vi.fn(),
      offEvent: vi.fn(),
      close: vi.fn(),
    },
  };
  vi.spyOn(api, "me").mockRejectedValue(
    new ApiError(
      403,
      "platform_access_not_granted",
      "Platform access has not been granted",
    ),
  );

  renderPage(<ProtectedLayout />);

  expect(await screen.findByText("Доступ ещё не открыт")).toBeInTheDocument();
  expect(
    screen.getByText(/Вернитесь в бота и завершите оплату/),
  ).toBeInTheDocument();
});
