import { afterEach, expect, it, vi } from "vitest";

import { BrowserPlatformAdapter } from "../src/platform/BrowserPlatformAdapter";
import { TelegramPlatformAdapter } from "../src/platform/TelegramPlatformAdapter";
import { telegramMiniAppLink } from "../src/platform/telegramLinks";

afterEach(() => {
  delete window.Telegram;
  delete (window as Window & { TelegramWebviewProxy?: unknown })
    .TelegramWebviewProxy;
  vi.restoreAllMocks();
});

it("BrowserPlatformAdapter безопасен без Telegram SDK", () => {
  const adapter = new BrowserPlatformAdapter();
  expect(adapter.getTelegramInitData()).toBeNull();
  expect(() => {
    adapter.showBackButton();
    adapter.hideBackButton();
    adapter.triggerSuccessFeedback();
    adapter.close();
  }).not.toThrow();
});

it("TelegramPlatformAdapter инициализирует SDK и подписывает BackButton", () => {
  const backCallback = vi.fn();
  const onClick = vi.fn();
  const offClick = vi.fn();
  const ready = vi.fn();
  const expand = vi.fn();
  (
    window as Window & {
      TelegramWebviewProxy?: { postEvent: () => void };
    }
  ).TelegramWebviewProxy = { postEvent: vi.fn() };
  window.Telegram = {
    WebApp: {
      initData: "query_id=test",
      colorScheme: "dark",
      BackButton: { show: vi.fn(), hide: vi.fn(), onClick, offClick },
      ready,
      expand,
      onEvent: vi.fn(),
      offEvent: vi.fn(),
      close: vi.fn(),
    },
  };

  const adapter = new TelegramPlatformAdapter();
  adapter.initialize();
  const unsubscribe = adapter.onBackButton(backCallback);
  unsubscribe();

  expect(adapter.getTelegramInitData()).toBe("query_id=test");
  expect(adapter.getColorScheme()).toBe("dark");
  expect(ready).toHaveBeenCalledOnce();
  expect(expand).toHaveBeenCalledOnce();
  expect(onClick).toHaveBeenCalledWith(backCallback);
  expect(offClick).toHaveBeenCalledWith(backCallback);
});

it("ссылка с сайта сразу запускает Main Mini App", () => {
  expect(telegramMiniAppLink("https://t.me/codewaste_bot")).toBe(
    "https://t.me/codewaste_bot?startapp",
  );
  expect(telegramMiniAppLink("https://t.me/codewaste_bot?startapp")).toBe(
    "https://t.me/codewaste_bot?startapp",
  );
});
