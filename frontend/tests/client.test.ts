import { afterEach, expect, it, vi } from "vitest";

import { apiRequest } from "../src/api/client";
import { clearDevUserId, setDevUserId } from "../src/features/auth/devAuth";

afterEach(() => {
  delete window.Telegram;
  clearDevUserId();
  vi.restoreAllMocks();
});

function successfulFetch() {
  return vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: true,
    json: async () => ({ ok: true }),
  } as Response);
}

it("передаёт Telegram initData в Authorization без localStorage", async () => {
  const fetchMock = successfulFetch();
  window.Telegram = {
    WebApp: {
      initData: "query_id=test&hash=signed",
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

  await apiRequest("/api/v1/me");

  const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
  expect(fetchMock.mock.calls[0]?.[1]?.credentials).toBe("include");
  expect(headers.get("Authorization")).toBe("tma query_id=test&hash=signed");
  expect(headers.has("X-Dev-User-Id")).toBe(false);
});

it("использует UUID-заголовок только как development fallback", async () => {
  const fetchMock = successfulFetch();
  setDevUserId("20000000-0000-4000-8000-000000000001");

  await apiRequest("/api/v1/me");

  const headers = fetchMock.mock.calls[0]?.[1]?.headers as Headers;
  expect(headers.get("X-Dev-User-Id")).toBe(
    "20000000-0000-4000-8000-000000000001",
  );
  expect(headers.has("Authorization")).toBe(false);
});
