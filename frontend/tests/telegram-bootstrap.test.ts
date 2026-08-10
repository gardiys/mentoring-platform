import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  getTelegramInitData,
  isTelegramLaunchContext,
  loadTelegramSdk,
  resetTelegramSdkLoaderForTests,
} from "../src/platform/telegramSdk";

const SDK_SELECTOR = "script[data-telegram-sdk]";

function clearTelegramEnvironment() {
  delete window.Telegram;
  delete (window as Window & { TelegramWebviewProxy?: unknown })
    .TelegramWebviewProxy;
  window.sessionStorage.removeItem("__telegram__initParams");
  window.history.replaceState({}, "", "/");
  document.querySelector(SDK_SELECTOR)?.remove();
  resetTelegramSdkLoaderForTests();
}

beforeEach(clearTelegramEnvironment);

afterEach(() => {
  vi.useRealTimers();
  clearTelegramEnvironment();
});

describe("Telegram SDK bootstrap", () => {
  it("does not request Telegram SDK in a regular browser", async () => {
    expect(isTelegramLaunchContext()).toBe(false);
    await expect(loadTelegramSdk()).resolves.toBe("not-needed");
    expect(document.querySelector(SDK_SELECTOR)).toBeNull();
  });

  it("loads the pinned same-origin SDK for Telegram launch parameters", async () => {
    window.history.replaceState(
      {},
      "",
      "/#tgWebAppData=query_id%3Dtest%26auth_date%3D1&tgWebAppPlatform=android&tgWebAppVersion=9.0",
    );

    const loading = loadTelegramSdk(window, document, 1_000);
    const script = document.querySelector<HTMLScriptElement>(SDK_SELECTOR);
    expect(script).not.toBeNull();
    expect(script?.src).toBe(
      `${window.location.origin}/vendor/telegram-web-app-2026-07-14.js`,
    );
    expect(script?.src).not.toContain("telegram.org");
    expect(getTelegramInitData()).toBe("query_id=test&auth_date=1");

    window.Telegram = { WebApp: { initData: "query_id=test&auth_date=1" } };
    script?.dispatchEvent(new Event("load"));
    await expect(loading).resolves.toBe("loaded");
  });

  it("detects a Telegram reload from SDK session storage", async () => {
    window.sessionStorage.setItem(
      "__telegram__initParams",
      JSON.stringify({
        tgWebAppData: "query_id=stored",
        tgWebAppPlatform: "tdesktop",
        tgWebAppVersion: "9.0",
      }),
    );

    expect(isTelegramLaunchContext()).toBe(true);
    expect(getTelegramInitData()).toBe("query_id=stored");
    const loading = loadTelegramSdk(window, document, 1_000);
    expect(document.querySelector(SDK_SELECTOR)).not.toBeNull();
    document.querySelector(SDK_SELECTOR)?.dispatchEvent(new Event("error"));
    await expect(loading).resolves.toBe("failed");
  });

  it("falls through after a bounded SDK timeout", async () => {
    vi.useFakeTimers();
    window.history.replaceState(
      {},
      "",
      "/#tgWebAppData=query_id%3Dtimeout&tgWebAppPlatform=ios",
    );

    const loading = loadTelegramSdk(window, document, 25);
    await vi.advanceTimersByTimeAsync(25);

    await expect(loading).resolves.toBe("timeout");
    expect(getTelegramInitData()).toBe("query_id=timeout");
  });

  it("does not classify an empty unknown SDK as Telegram", () => {
    window.Telegram = {
      WebApp: { initData: "", platform: "unknown" },
    };

    expect(isTelegramLaunchContext()).toBe(false);
    expect(getTelegramInitData()).toBeNull();
  });

  it("keeps the application HTML free from blocking Telegram requests", () => {
    const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8");

    expect(html).not.toContain("https://telegram.org/js/telegram-web-app.js");
    expect(html).toContain(
      '<script type="module" src="/src/main.tsx"></script>',
    );
  });
});
