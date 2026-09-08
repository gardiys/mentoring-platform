import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AppLayout } from "../src/components/AppLayout";
import { RoleGuard } from "../src/components/RoleGuard";
import { copilotApi, type CopilotRelease } from "../src/features/copilot/api";
import { CopilotPage } from "../src/pages/CopilotPage";
import { renderPage } from "./render";

const user = {
  id: "20000000-0000-4000-8000-000000000001",
  telegram_id: 987654321,
  first_name: "Иван",
  last_name: null,
  email: null,
  role: "admin" as const,
  onboarding_completed_at: "2026-08-01T00:00:00Z",
  is_active: true,
};
const release: CopilotRelease = {
  id: "win-x64",
  os: "windows",
  arch: "x64",
  version: "0.1.0",
  filename: "Copilot.exe",
  size_bytes: 123456,
  sha256: "a".repeat(64),
  signed: false,
};
afterEach(() => vi.restoreAllMocks());

it("показывает описание и варианты скачивания для трёх платформ", async () => {
  vi.spyOn(copilotApi, "releases").mockResolvedValue({
    releases: [
      release,
      { ...release, id: "mac-arm64", os: "macos", arch: "arm64" },
      { ...release, id: "mac-x64", os: "macos" },
    ],
  });
  renderPage(<CopilotPage />);
  expect(
    await screen.findByRole("button", { name: "Скачать для Windows" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Скачать для Mac · Apple Silicon" }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Скачать для Mac · Intel" }),
  ).toBeInTheDocument();
  expect(
    screen.getByText(/Для учеников Copilot ещё не открыт/),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Как начать" }),
  ).toBeInTheDocument();
});

it("скачивает защищённый файл и показывает ошибку с возможностью повтора", async () => {
  vi.spyOn(copilotApi, "releases").mockResolvedValue({ releases: [release] });
  const download = vi
    .spyOn(copilotApi, "download")
    .mockRejectedValue(new Error("Скачивание прервалось"));
  renderPage(<CopilotPage />);
  const button = await screen.findByRole("button", {
    name: "Скачать для Windows",
  });
  await userEvent.click(button);
  expect(await screen.findByText("Скачивание прервалось")).toBeInTheDocument();
  expect(download).toHaveBeenCalledWith(
    "win-x64",
    expect.any(AbortSignal),
    expect.any(Function),
  );
  expect(button).not.toBeDisabled();
});

it("объясняет отсутствие загруженных сборок", async () => {
  vi.spyOn(copilotApi, "releases").mockResolvedValue({ releases: [] });
  renderPage(<CopilotPage />);
  expect(await screen.findByText("Сборки скоро появятся")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /Скачать/ }),
  ).not.toBeInTheDocument();
});

it.each(["student", "mentor"] as const)(
  "не пускает роль %s по прямому адресу",
  async (role) => {
    vi.spyOn(api, "me").mockResolvedValue({ ...user, role });
    const listing = vi.spyOn(copilotApi, "releases");
    renderPage(
      <RoleGuard roles={["admin"]} />,
      "/copilot",
      "/copilot",
      <CopilotPage />,
    );
    expect(await screen.findByText("Раздел недоступен")).toBeInTheDocument();
    expect(listing).not.toHaveBeenCalled();
  },
);

it.each(["student", "admin"] as const)(
  "показывает пункт меню только администратору (%s)",
  async (role) => {
    vi.spyOn(api, "me").mockResolvedValue({ ...user, role });
    vi.spyOn(api, "notifications").mockResolvedValue({
      items: [],
      total: 0,
      unread_count: 0,
      limit: 20,
      offset: 0,
    });
    renderPage(<AppLayout />);
    await waitFor(() => expect(screen.getByText("Иван")).toBeInTheDocument());
    expect(Boolean(screen.queryByRole("link", { name: /Copilot/ }))).toBe(
      role === "admin",
    );
  },
);
