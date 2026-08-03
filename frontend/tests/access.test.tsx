import { screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";

import { ApiError } from "../src/api/client";
import { api } from "../src/api/endpoints";
import { ProtectedLayout } from "../src/components/ProtectedLayout";
import { RoleGuard } from "../src/components/RoleGuard";
import { renderPage } from "./render";

const browserUser = {
  id: "20000000-0000-4000-8000-000000000001",
  telegram_id: 987654321,
  first_name: "Иван",
  last_name: null,
  email: null,
  role: "student" as const,
  onboarding_completed_at: "2026-08-01T00:00:00Z",
  is_active: true,
};

afterEach(() => {
  delete window.Telegram;
  vi.restoreAllMocks();
});

it("проверяет серверную cookie-сессию и без Telegram initData", async () => {
  const me = vi.spyOn(api, "me").mockResolvedValue(browserUser);

  renderPage(<ProtectedLayout />);

  await waitFor(() => expect(me).toHaveBeenCalledOnce());
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

it("объясняет ученику, что администратор приостановил доступ", async () => {
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
    new ApiError(403, "student_access_suspended", "Access suspended"),
  );

  renderPage(<ProtectedLayout />);

  expect(await screen.findByText("Доступ закрыт")).toBeInTheDocument();
  expect(screen.getByText(/Свяжитесь с ментором/)).toBeInTheDocument();
});

it("не пускает ученика в административный раздел", async () => {
  vi.spyOn(api, "me").mockResolvedValue(browserUser);

  renderPage(
    <RoleGuard roles={["admin"]} />,
    "/admin",
    "/admin",
    <div>Секретная админка</div>,
  );

  expect(await screen.findByText("Раздел недоступен")).toBeInTheDocument();
  expect(screen.queryByText("Секретная админка")).not.toBeInTheDocument();
});

it("пускает ментора в менторский раздел, но не в административный", async () => {
  vi.spyOn(api, "me").mockResolvedValue({ ...browserUser, role: "mentor" });

  const mentorView = renderPage(
    <RoleGuard roles={["mentor", "admin"]} />,
    "/mentor",
    "/mentor",
    <div>Мои ученики</div>,
  );
  expect(await screen.findByText("Мои ученики")).toBeInTheDocument();
  mentorView.unmount();

  renderPage(
    <RoleGuard roles={["admin"]} />,
    "/admin",
    "/admin",
    <div>Секретная админка</div>,
  );
  expect(await screen.findByText("Раздел недоступен")).toBeInTheDocument();
});

it("пускает администратора в административный раздел", async () => {
  vi.spyOn(api, "me").mockResolvedValue({ ...browserUser, role: "admin" });

  renderPage(
    <RoleGuard roles={["admin"]} />,
    "/admin",
    "/admin",
    <div>Секретная админка</div>,
  );

  expect(await screen.findByText("Секретная админка")).toBeInTheDocument();
});
