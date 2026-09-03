import { afterEach, describe, expect, it, vi } from "vitest";

import { openExternalResource } from "../src/utils/openExternalResource";

type PopupMock = {
  closed: boolean;
  close: ReturnType<typeof vi.fn>;
  location: { replace: ReturnType<typeof vi.fn> };
  opener: unknown;
};

function mockPopup(): PopupMock {
  const popup: PopupMock = {
    closed: false,
    close: vi.fn(),
    location: { replace: vi.fn() },
    opener: window,
  };
  vi.spyOn(window, "open").mockReturnValue(popup as unknown as Window);
  return popup;
}

afterEach(() => {
  delete (window as Window & { TelegramWebviewProxy?: unknown })
    .TelegramWebviewProxy;
  delete window.Telegram;
  vi.restoreAllMocks();
});

describe("openExternalResource", () => {
  it("opens an absolute HTTPS URL without retaining the opener", async () => {
    const popup = mockPopup();

    await openExternalResource(
      Promise.resolve("https://files.example.test/a b"),
    );

    expect(popup.opener).toBeNull();
    expect(popup.location.replace).toHaveBeenCalledWith(
      "https://files.example.test/a%20b",
    );
    expect(popup.close).not.toHaveBeenCalled();
  });

  it("allows an HTTP MinIO URL on localhost in development", async () => {
    const popup = mockPopup();

    await openExternalResource(
      Promise.resolve("http://localhost:9000/private/resume.pdf?signature=test"),
    );

    expect(popup.location.replace).toHaveBeenCalledWith(
      "http://localhost:9000/private/resume.pdf?signature=test",
    );
    expect(popup.close).not.toHaveBeenCalled();
  });

  it.each([
    "/relative/file.pdf",
    "http://files.example.test/file.pdf",
    "https://user:password@files.example.test/file.pdf",
    "javascript:alert(document.domain)",
    "data:text/html,unsafe",
  ])("rejects unsafe external URL %s and closes the popup", async (url) => {
    const popup = mockPopup();

    await expect(openExternalResource(Promise.resolve(url))).rejects.toThrow(
      "Разрешены только абсолютные HTTPS-ссылки",
    );

    expect(popup.location.replace).not.toHaveBeenCalled();
    expect(popup.close).toHaveBeenCalledOnce();
  });

  it("closes the popup when obtaining the URL fails", async () => {
    const popup = mockPopup();
    const failure = new Error("request failed");

    await expect(openExternalResource(Promise.reject(failure))).rejects.toBe(
      failure,
    );

    expect(popup.location.replace).not.toHaveBeenCalled();
    expect(popup.close).toHaveBeenCalledOnce();
  });

  it("opens the resolved URL through Telegram without exposing about:blank", async () => {
    const openLink = vi.fn();
    (window as Window & { TelegramWebviewProxy?: unknown }).TelegramWebviewProxy = {
      postEvent: vi.fn(),
    };
    window.Telegram = { WebApp: { openLink } };
    const windowOpen = vi.spyOn(window, "open");

    await openExternalResource(
      Promise.resolve("https://secure.tochka.test/payment"),
    );

    expect(windowOpen).not.toHaveBeenCalled();
    expect(openLink).toHaveBeenCalledOnce();
    expect(openLink).toHaveBeenCalledWith(
      "https://secure.tochka.test/payment",
    );
  });
});
