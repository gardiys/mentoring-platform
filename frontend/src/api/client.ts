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

export interface UploadOptions {
  onProgress?: (percent: number) => void;
  signal?: AbortSignal;
}

function networkError(message: string, error?: unknown): ApiError {
  const aborted = error instanceof DOMException && error.name === "AbortError";
  return new ApiError(
    0,
    aborted ? "request_aborted" : "network_error",
    aborted ? "Загрузка отменена" : message,
  );
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

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...init,
      headers,
      credentials: "include",
    });
  } catch (error) {
    throw networkError(
      "Не удалось связаться с сервером. Проверьте подключение и повторите попытку.",
      error,
    );
  }
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
  options?: UploadOptions,
): Promise<void> {
  const body = new FormData();
  Object.entries(intent.fields).forEach(([key, value]) =>
    body.append(key, value),
  );
  body.append("file", file);
  if (options?.onProgress || options?.signal) {
    return uploadPresignedPostWithProgress(intent.upload_url, body, options);
  }

  let response: Response;
  try {
    response = await fetch(intent.upload_url, { method: "POST", body });
  } catch (error) {
    throw networkError(
      "Не удалось загрузить файл в хранилище. Проверьте подключение и повторите попытку.",
      error,
    );
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      "interview_s3_upload_failed",
      "Не удалось загрузить файл в хранилище",
    );
  }
}

function uploadPresignedPostWithProgress(
  url: string,
  body: FormData,
  options: UploadOptions,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const abort = () => request.abort();
    const cleanup = () => options.signal?.removeEventListener("abort", abort);

    request.open("POST", url);
    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable || event.total <= 0) return;
      options.onProgress?.(
        Math.min(100, Math.round((event.loaded / event.total) * 100)),
      );
    });
    request.addEventListener("load", () => {
      cleanup();
      if (request.status >= 200 && request.status < 300) {
        options.onProgress?.(100);
        resolve();
        return;
      }
      reject(
        new ApiError(
          request.status,
          "interview_s3_upload_failed",
          "Не удалось загрузить файл в хранилище",
        ),
      );
    });
    request.addEventListener("error", () => {
      cleanup();
      reject(
        networkError(
          "Не удалось загрузить файл в хранилище. Проверьте подключение и повторите попытку.",
        ),
      );
    });
    request.addEventListener("abort", () => {
      cleanup();
      reject(new ApiError(0, "request_aborted", "Загрузка отменена"));
    });

    if (options.signal?.aborted) {
      cleanup();
      reject(new ApiError(0, "request_aborted", "Загрузка отменена"));
      return;
    }
    options.signal?.addEventListener("abort", abort, { once: true });
    try {
      request.send(body);
    } catch (error) {
      cleanup();
      reject(
        networkError(
          "Не удалось загрузить файл в хранилище. Проверьте подключение и повторите попытку.",
          error,
        ),
      );
    }
  });
}
