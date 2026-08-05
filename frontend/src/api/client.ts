import { getDevUserId } from "../features/auth/devAuth";
import { getTelegramInitData } from "../platform/telegramSdk";

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
  onStatus?: (status: UploadStatus) => void;
  signal?: AbortSignal;
}

export type UploadPhase = "preparing" | "uploading" | "finalizing";

export interface UploadStatus {
  phase: UploadPhase;
  percent: number;
  uploadedBytes: number;
  totalBytes: number;
  bytesPerSecond: number | null;
  etaSeconds: number | null;
}

export interface LegacyUploadIntent {
  upload_protocol?: "legacy-post";
  upload_url: string;
  fields: Record<string, string>;
  storage_key: string;
  filename: string;
  content_type: string;
  size: number;
  expires_in: number;
}

export interface MultipartUploadPartIntent {
  part_number: number;
  upload_url: string;
  headers: Record<string, string>;
}

export interface MultipartUploadIntent {
  upload_protocol: "multipart-v1";
  upload_id: string;
  upload_token: string;
  storage_key: string;
  filename: string;
  content_type: string;
  size: number;
  part_size: number;
  part_count: number;
  parts: MultipartUploadPartIntent[];
  expires_in: number;
  abort_url: string;
}

export type StorageUploadIntent = LegacyUploadIntent | MultipartUploadIntent;

export interface MultipartUploadCompletion {
  upload_protocol: "multipart-v1";
  upload_id: string;
  upload_token: string;
  parts: { part_number: number; etag: string }[];
}

const MULTIPART_CONCURRENCY = 3;
const MULTIPART_RETRIES = 3;

export function isMultipartUploadIntent(
  intent: StorageUploadIntent,
): intent is MultipartUploadIntent {
  return intent.upload_protocol === "multipart-v1";
}

export function uploadStatus(
  phase: UploadPhase,
  file: File,
  options?: UploadOptions,
  progress?: {
    loaded: number;
    total: number;
    startedAt: number;
  },
): void {
  const loaded = progress?.loaded ?? (phase === "finalizing" ? file.size : 0);
  const total = progress?.total ?? file.size;
  const elapsedSeconds = progress
    ? Math.max((performance.now() - progress.startedAt) / 1000, 0.001)
    : 0;
  const bytesPerSecond =
    phase === "uploading" && loaded > 0 ? loaded / elapsedSeconds : null;
  const etaSeconds =
    bytesPerSecond && bytesPerSecond > 0
      ? Math.max(0, (total - loaded) / bytesPerSecond)
      : null;
  const percent =
    phase === "finalizing"
      ? 100
      : total > 0
        ? Math.min(100, Math.round((loaded / total) * 100))
        : 0;
  options?.onProgress?.(percent);
  options?.onStatus?.({
    phase,
    percent,
    uploadedBytes: loaded,
    totalBytes: total,
    bytesPerSecond,
    etaSeconds,
  });
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
  const telegramInitData = getTelegramInitData();
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
  const startedAt = performance.now();
  const body = new FormData();
  Object.entries(intent.fields).forEach(([key, value]) =>
    body.append(key, value),
  );
  body.append("file", file);
  if (options?.onProgress || options?.onStatus || options?.signal) {
    return uploadPresignedPostWithProgress(
      intent.upload_url,
      body,
      file,
      startedAt,
      options,
    );
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

export async function uploadStorageIntent(
  intent: StorageUploadIntent,
  file: File,
  options?: UploadOptions,
): Promise<MultipartUploadCompletion | null> {
  if (!isMultipartUploadIntent(intent)) {
    await uploadPresignedPost(intent, file, options);
    return null;
  }
  return uploadMultipartIntent(intent, file, options);
}

export async function abortMultipartUpload(
  intent: MultipartUploadIntent,
): Promise<void> {
  await apiRequest<void>(intent.abort_url, {
    method: "POST",
    body: JSON.stringify({
      upload_id: intent.upload_id,
      upload_token: intent.upload_token,
      storage_key: intent.storage_key,
    }),
  });
}

async function uploadMultipartIntent(
  intent: MultipartUploadIntent,
  file: File,
  options?: UploadOptions,
): Promise<MultipartUploadCompletion> {
  validateMultipartIntent(intent, file);
  const startedAt = performance.now();
  const uploadedByPart = new Map<number, number>();
  const completedParts = new Map<number, string>();
  const localController = new AbortController();
  const abortActiveUploads = () => localController.abort();
  options?.signal?.addEventListener("abort", abortActiveUploads, {
    once: true,
  });

  const emitProgress = () => {
    const loaded = [...uploadedByPart.values()].reduce(
      (total, value) => total + value,
      0,
    );
    uploadStatus("uploading", file, options, {
      loaded: Math.min(file.size, loaded),
      total: file.size,
      startedAt,
    });
  };

  let nextPartIndex = 0;
  const worker = async () => {
    while (nextPartIndex < intent.parts.length) {
      const part = intent.parts[nextPartIndex++];
      if (!part) return;
      const start = (part.part_number - 1) * intent.part_size;
      const end = Math.min(file.size, start + intent.part_size);
      const chunk = file.slice(start, end);
      const etag = await uploadMultipartPartWithRetry(
        part,
        chunk,
        (loaded) => {
          uploadedByPart.set(part.part_number, loaded);
          emitProgress();
        },
        options?.signal,
        localController.signal,
      );
      uploadedByPart.set(part.part_number, chunk.size);
      completedParts.set(part.part_number, etag);
      emitProgress();
    }
  };

  try {
    emitProgress();
    await Promise.all(
      Array.from(
        { length: Math.min(MULTIPART_CONCURRENCY, intent.parts.length) },
        () => worker(),
      ),
    );
  } catch (error) {
    localController.abort();
    throw error;
  } finally {
    options?.signal?.removeEventListener("abort", abortActiveUploads);
  }

  return {
    upload_protocol: "multipart-v1",
    upload_id: intent.upload_id,
    upload_token: intent.upload_token,
    parts: [...completedParts.entries()]
      .sort(([left], [right]) => left - right)
      .map(([part_number, etag]) => ({ part_number, etag })),
  };
}

function validateMultipartIntent(intent: MultipartUploadIntent, file: File) {
  const expectedPartCount = Math.ceil(file.size / intent.part_size);
  const partNumbers = intent.parts.map((part) => part.part_number);
  if (
    intent.size !== file.size ||
    intent.part_size <= 0 ||
    intent.part_count !== expectedPartCount ||
    intent.parts.length !== expectedPartCount ||
    new Set(partNumbers).size !== expectedPartCount ||
    partNumbers.some(
      (partNumber) => partNumber < 1 || partNumber > expectedPartCount,
    )
  ) {
    throw new ApiError(
      0,
      "invalid_multipart_upload_intent",
      "Хранилище вернуло некорректные параметры загрузки",
    );
  }
}

async function uploadMultipartPartWithRetry(
  part: MultipartUploadPartIntent,
  chunk: Blob,
  onProgress: (loaded: number) => void,
  userSignal?: AbortSignal,
  localSignal?: AbortSignal,
): Promise<string> {
  for (let retry = 0; retry <= MULTIPART_RETRIES; retry += 1) {
    try {
      return await uploadMultipartPart(
        part,
        chunk,
        onProgress,
        userSignal,
        localSignal,
      );
    } catch (error) {
      if (
        retry >= MULTIPART_RETRIES ||
        !isRetryableUploadError(error) ||
        userSignal?.aborted ||
        localSignal?.aborted
      ) {
        throw error;
      }
      onProgress(0);
      await abortableDelay(500 * 2 ** retry, userSignal, localSignal);
    }
  }
  throw new ApiError(0, "multipart_upload_failed", "Не удалось загрузить файл");
}

function uploadMultipartPart(
  part: MultipartUploadPartIntent,
  chunk: Blob,
  onProgress: (loaded: number) => void,
  userSignal?: AbortSignal,
  localSignal?: AbortSignal,
): Promise<string> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const abort = () => request.abort();
    const cleanup = () => {
      userSignal?.removeEventListener("abort", abort);
      localSignal?.removeEventListener("abort", abort);
    };
    request.open("PUT", part.upload_url);
    Object.entries(part.headers).forEach(([name, value]) =>
      request.setRequestHeader(name, value),
    );
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable)
        onProgress(Math.min(chunk.size, event.loaded));
    });
    request.addEventListener("load", () => {
      cleanup();
      if (request.status < 200 || request.status >= 300) {
        reject(
          new ApiError(
            request.status,
            "multipart_part_upload_failed",
            "Не удалось загрузить часть файла в хранилище",
          ),
        );
        return;
      }
      const etag = request.getResponseHeader("ETag")?.trim();
      if (!etag) {
        reject(
          new ApiError(
            0,
            "multipart_etag_missing",
            "Хранилище не вернуло ETag. Проверьте CORS ExposeHeaders для ETag.",
          ),
        );
        return;
      }
      onProgress(chunk.size);
      resolve(etag);
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

    if (userSignal?.aborted || localSignal?.aborted) {
      cleanup();
      reject(new ApiError(0, "request_aborted", "Загрузка отменена"));
      return;
    }
    userSignal?.addEventListener("abort", abort, { once: true });
    localSignal?.addEventListener("abort", abort, { once: true });
    try {
      request.send(chunk);
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

function isRetryableUploadError(error: unknown) {
  return (
    error instanceof ApiError &&
    error.code !== "request_aborted" &&
    error.code !== "multipart_etag_missing" &&
    (error.status === 0 ||
      error.status === 408 ||
      error.status === 425 ||
      error.status === 429 ||
      error.status >= 500)
  );
}

function abortableDelay(
  milliseconds: number,
  userSignal?: AbortSignal,
  localSignal?: AbortSignal,
) {
  return new Promise<void>((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      cleanup();
      resolve();
    }, milliseconds);
    const abort = () => {
      window.clearTimeout(timeout);
      cleanup();
      reject(new ApiError(0, "request_aborted", "Загрузка отменена"));
    };
    const cleanup = () => {
      userSignal?.removeEventListener("abort", abort);
      localSignal?.removeEventListener("abort", abort);
    };
    if (userSignal?.aborted || localSignal?.aborted) {
      abort();
      return;
    }
    userSignal?.addEventListener("abort", abort, { once: true });
    localSignal?.addEventListener("abort", abort, { once: true });
  });
}

function uploadPresignedPostWithProgress(
  url: string,
  body: FormData,
  file: File,
  startedAt: number,
  options: UploadOptions,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const abort = () => request.abort();
    const cleanup = () => options.signal?.removeEventListener("abort", abort);

    request.open("POST", url);
    request.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable || event.total <= 0) return;
      const loaded = Math.min(
        file.size,
        Math.max(0, file.size * (event.loaded / event.total)),
      );
      uploadStatus("uploading", file, options, {
        loaded,
        total: file.size,
        startedAt,
      });
    });
    request.addEventListener("load", () => {
      cleanup();
      if (request.status >= 200 && request.status < 300) {
        uploadStatus("uploading", file, options, {
          loaded: file.size,
          total: file.size,
          startedAt,
        });
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
