import { readFileSync } from "node:fs";
import { runInNewContext } from "node:vm";
import { Button, Modal, useMantineColorScheme } from "@mantine/core";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { COLOR_SCHEME_STORAGE_KEY } from "../src/app/colorScheme";
import { AppProviders } from "../src/app/providers";
import { ThemeToggle } from "../src/components/ThemeToggle";

beforeEach(() => {
  localStorage.removeItem(COLOR_SCHEME_STORAGE_KEY);
  document.head.insertAdjacentHTML(
    "beforeend",
    '<meta name="theme-color" content="#101D2D"><meta name="color-scheme" content="dark">',
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.removeItem(COLOR_SCHEME_STORAGE_KEY);
  document
    .querySelectorAll('meta[name="theme-color"], meta[name="color-scheme"]')
    .forEach((meta) => meta.remove());
});

function Preview() {
  const { colorScheme, clearColorScheme } = useMantineColorScheme();
  return (
    <>
      <ThemeToggle />
      <Button onClick={clearColorScheme}>Сбросить тему</Button>
      <Modal opened onClose={() => undefined} title="Настройки">
        <span>Тема окна: {colorScheme}</span>
      </Modal>
    </>
  );
}

it.each([null, "auto", "invalid"])(
  "открывает тёмную тему без явного выбора (%s), независимо от системной темы",
  (saved) => {
    if (saved) localStorage.setItem(COLOR_SCHEME_STORAGE_KEY, saved);
    render(
      <AppProviders>
        <ThemeToggle />
      </AppProviders>,
    );
    expect(document.documentElement).toHaveAttribute(
      "data-mantine-color-scheme",
      "dark",
    );
    expect(
      screen.getByRole("button", { name: "Включить светлую тему" }),
    ).toBeInTheDocument();
  },
);

it("переключает тему в окнах, сохраняет выбор и восстанавливает после перезагрузки", async () => {
  const user = userEvent.setup();
  const first = render(
    <AppProviders>
      <Preview />
    </AppProviders>,
  );
  await user.click(
    screen.getByRole("button", { name: "Включить светлую тему" }),
  );
  expect(document.documentElement).toHaveAttribute(
    "data-mantine-color-scheme",
    "light",
  );
  expect(screen.getByText("Тема окна: light")).toBeInTheDocument();
  expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe("light");
  expect(document.querySelector('meta[name="color-scheme"]')).toHaveAttribute(
    "content",
    "light",
  );
  first.unmount();
  render(
    <AppProviders>
      <Preview />
    </AppProviders>,
  );
  expect(
    screen.getByRole("button", { name: "Включить тёмную тему" }),
  ).toBeInTheDocument();
  await user.click(
    screen.getByRole("button", { name: "Включить тёмную тему" }),
  );
  expect(document.documentElement).toHaveAttribute(
    "data-mantine-color-scheme",
    "dark",
  );
  expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBe("dark");
});

it("синхронизирует выбор между вкладками и возвращает тёмную тему при сбросе", async () => {
  render(
    <AppProviders>
      <Preview />
    </AppProviders>,
  );
  window.dispatchEvent(
    new StorageEvent("storage", {
      storageArea: localStorage,
      key: COLOR_SCHEME_STORAGE_KEY,
      newValue: "light",
    }),
  );
  await screen.findByText("Тема окна: light");
  await userEvent.click(screen.getByRole("button", { name: "Сбросить тему" }));
  await waitFor(() =>
    expect(document.documentElement).toHaveAttribute(
      "data-mantine-color-scheme",
      "dark",
    ),
  );
  expect(localStorage.getItem(COLOR_SCHEME_STORAGE_KEY)).toBeNull();
});

it("позволяет менять тему при недоступном хранилище браузера", async () => {
  vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new Error("blocked");
  });
  render(
    <AppProviders>
      <ThemeToggle />
    </AppProviders>,
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Включить светлую тему" }),
  );
  expect(document.documentElement).toHaveAttribute(
    "data-mantine-color-scheme",
    "light",
  );
});

it.each([null, "light", "dark", "auto", "invalid", "blocked"])(
  "применяет тему до загрузки приложения (%s)",
  (saved) => {
    const html = readFileSync("index.html", "utf8");
    const script = html.match(/<script>([\s\S]*?)<\/script>/)![1]!;
    runInNewContext(script, {
      document,
      localStorage: {
        getItem: () => {
          if (saved === "blocked") throw new Error("blocked");
          return saved;
        },
      },
    });
    const expected = saved === "light" ? "light" : "dark";
    expect(document.documentElement).toHaveAttribute(
      "data-mantine-color-scheme",
      expected,
    );
    expect(document.querySelector('meta[name="theme-color"]')).toHaveAttribute(
      "content",
      expected === "light" ? "#FAF7F1" : "#101D2D",
    );
  },
);
