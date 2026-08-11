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

type WindowWithBridges = Window & {
  TelegramWebviewProxy?: { postEvent: () => void };
  webkit?: {
    messageHandlers?: {
      TelegramWebviewProxy?: { postMessage: () => void };
    };
  };
};

function clearTelegramEnvironment() {
  delete window.Telegram;
  delete (window as WindowWithBridges).TelegramWebviewProxy;
  delete (window as WindowWithBridges).webkit;
  window.sessionStorage.removeItem("__telegram__initParams");
  window.history.replaceState({}, "", "/");
  document.querySelector(SDK_SELECTOR)?.remove();
  resetTelegramSdkLoaderForTests();
}

function withProperties(properties: Record<string, unknown>): Window {
  const result = Object.create(window) as Window;
  for (const [key, value] of Object.entries(properties)) {
    Object.defineProperty(result, key, {
      configurable: true,
      value,
    });
  }
  return result;
}

function telegramFrame(parentOrigin: string, ancestorOrigin?: string): Window {
  return withProperties({
    parent: {},
    location: {
      hash: "#tgWebAppData=query_id%3Dweb%26auth_date%3D1&tgWebAppPlatform=web",
      search: "",
      ancestorOrigins: {
        length: ancestorOrigin ? 1 : 0,
        item: () => ancestorOrigin ?? null,
      },
    },
    document: { referrer: `${parentOrigin}/k/` },
    sessionStorage: window.sessionStorage,
  });
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

  it("ignores forged URL and stored launch parameters in a regular browser", async () => {
    window.history.replaceState(
      {},
      "",
      "/#tgWebAppData=query_id%3Dforged&tgWebAppPlatform=android",
    );
    window.sessionStorage.setItem(
      "__telegram__initParams",
      JSON.stringify({ tgWebAppData: "query_id=stored" }),
    );

    expect(isTelegramLaunchContext()).toBe(false);
    expect(getTelegramInitData()).toBeNull();
    await expect(loadTelegramSdk()).resolves.toBe("not-needed");
    expect(document.querySelector(SDK_SELECTOR)).toBeNull();
  });

  it("loads the pinned same-origin SDK for a native Android bridge", async () => {
    (window as WindowWithBridges).TelegramWebviewProxy = {
      postEvent: vi.fn(),
    };
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

  it("accepts launch data from a direct web.telegram.org iframe", () => {
    const framedWindow = telegramFrame("https://web.telegram.org");

    expect(isTelegramLaunchContext(framedWindow)).toBe(true);
    expect(getTelegramInitData(framedWindow)).toBe("query_id=web&auth_date=1");
  });

  it("rejects launch data from an untrusted iframe", () => {
    const framedWindow = telegramFrame("https://web.telegram.org.evil.test");

    expect(isTelegramLaunchContext(framedWindow)).toBe(false);
    expect(getTelegramInitData(framedWindow)).toBeNull();
  });

  it("requires the immediate iframe parent to be Telegram Web", () => {
    const nestedFrame = telegramFrame(
      "https://web.telegram.org",
      "https://intermediary.example.test",
    );

    expect(isTelegramLaunchContext(nestedFrame)).toBe(false);
    expect(getTelegramInitData(nestedFrame)).toBeNull();
  });

  it("recognizes native external.notify and WebKit bridges", () => {
    const externalWindow = withProperties({
      external: { notify: vi.fn() },
      Telegram: { WebApp: { initData: "query_id=external" } },
    });
    const webkitWindow = withProperties({
      webkit: {
        messageHandlers: {
          TelegramWebviewProxy: { postMessage: vi.fn() },
        },
      },
      Telegram: { WebApp: { initData: "query_id=webkit" } },
    });

    expect(isTelegramLaunchContext(externalWindow)).toBe(true);
    expect(isTelegramLaunchContext(webkitWindow)).toBe(true);
    expect(getTelegramInitData(externalWindow)).toBe("query_id=external");
    expect(getTelegramInitData(webkitWindow)).toBe("query_id=webkit");
  });

  it("detects a native Telegram reload from SDK session storage", async () => {
    (window as WindowWithBridges).TelegramWebviewProxy = {
      postEvent: vi.fn(),
    };
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

  it("falls through after a bounded SDK timeout in a native context", async () => {
    vi.useFakeTimers();
    (window as WindowWithBridges).TelegramWebviewProxy = {
      postEvent: vi.fn(),
    };
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

  it("does not trust a standalone SDK object in a regular browser", () => {
    window.Telegram = {
      WebApp: { initData: "query_id=forged", platform: "android" },
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
