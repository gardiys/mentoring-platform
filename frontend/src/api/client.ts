import { getDevUserId } from "../features/auth/devAuth";

export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export function resolveApiUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  return new URL(path, API_URL || window.location.origin).toString();
}

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

function authenticatedHeaders(init?: RequestInit): Headers {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  const telegramInitData = window.Telegram?.WebApp?.initData;
  if (telegramInitData) {
    headers.set("Authorization", `tma ${telegramInitData}`);
  } else if (import.meta.env.DEV) {
    const userId = getDevUserId();
    if (userId) headers.set("X-Dev-User-Id", userId);
  }
  return headers;
}

export async function apiRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const headers = authenticatedHeaders(init);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
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

export async function uploadPresignedPost(
  intent: { upload_url: string; fields: Record<string, string> },
  file: File,
): Promise<void> {
  const body = new FormData();
  Object.entries(intent.fields).forEach(([key, value]) =>
    body.append(key, value),
  );
  body.append("file", file);
  const response = await fetch(intent.upload_url, { method: "POST", body });
  if (!response.ok) {
    throw new ApiError(
      response.status,
      "interview_s3_upload_failed",
      "Не удалось загрузить файл в хранилище",
    );
  }
}
