import { getDevUserId } from "../features/auth/devAuth";

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

interface ErrorDetail {
  code: string;
  message: string;
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function isErrorDetail(value: unknown): value is { detail: ErrorDetail } {
  if (typeof value !== "object" || value === null || !("detail" in value))
    return false;
  const detail = value.detail;
  return (
    typeof detail === "object" &&
    detail !== null &&
    "code" in detail &&
    typeof detail.code === "string" &&
    "message" in detail &&
    typeof detail.message === "string"
  );
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  const telegramInitData = window.Telegram?.WebApp?.initData;
  if (telegramInitData) {
    headers.set("Authorization", `tma ${telegramInitData}`);
  } else if (import.meta.env.DEV) {
    const userId = getDevUserId();
    if (userId) headers.set("X-Dev-User-Id", userId);
  }

  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
  });
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (isErrorDetail(payload)) {
      throw new ApiError(
        response.status,
        payload.detail.code,
        payload.detail.message,
      );
    }
    throw new ApiError(
      response.status,
      "unexpected_error",
      "Не удалось выполнить запрос",
    );
  }
  return payload as T;
}
