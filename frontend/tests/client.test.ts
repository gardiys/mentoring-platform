import { afterEach, expect, it, vi } from "vitest";

import {
  apiRequest,
  uploadPresignedPost,
  uploadStorageIntent,
} from "../src/api/client";
import { clearDevUserId, setDevUserId } from "../src/features/auth/devAuth";

afterEach(() => {
  vi.useRealTimers();
  delete window.Telegram;
  clearDevUserId();
  vi.unstubAllGlobals();
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

it("загружает файл напрямую по подписанной S3 POST-форме", async () => {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: true,
    status: 204,
  } as Response);
  const file = new File(["video"], "interview.mp4", { type: "video/mp4" });

  await uploadPresignedPost(
    {
      upload_url: "http://localhost:9000/mentoring-platform",
      fields: { key: "pending/media/user/id", policy: "signed" },
    },
    file,
  );

  const body = fetchMock.mock.calls[0]?.[1]?.body as FormData;
  expect(fetchMock).toHaveBeenCalledWith(
    "http://localhost:9000/mentoring-platform",
    expect.objectContaining({ method: "POST" }),
  );
  expect(body.get("key")).toBe("pending/media/user/id");
  expect(body.get("file")).toBe(file);
});

it("преобразует сетевую ошибку API в понятную ошибку платформы", async () => {
  vi.spyOn(globalThis, "fetch").mockRejectedValue(
    new TypeError("Failed to fetch"),
  );

  await expect(apiRequest("/api/v1/me")).rejects.toMatchObject({
    status: 0,
    code: "network_error",
    message:
      "Не удалось связаться с сервером. Проверьте подключение и повторите попытку.",
  });
});

it("показывает прогресс загрузки подписанной S3 POST-формы", async () => {
  type Listener = (event: ProgressEvent) => void;
  const listeners = new Map<string, Listener>();
  const uploadListeners = new Map<string, Listener>();

  class XMLHttpRequestMock {
    status = 204;
    upload = {
      addEventListener: (name: string, listener: Listener) =>
        uploadListeners.set(name, listener),
    };
    open = vi.fn();
    addEventListener(name: string, listener: Listener) {
      listeners.set(name, listener);
    }
    send = vi.fn(() => {
      uploadListeners.get("progress")?.({
        lengthComputable: true,
        loaded: 5,
        total: 10,
      } as ProgressEvent);
      listeners.get("load")?.({} as ProgressEvent);
    });
    abort = vi.fn(() => listeners.get("abort")?.({} as ProgressEvent));
  }

  vi.stubGlobal("XMLHttpRequest", XMLHttpRequestMock);
  const onProgress = vi.fn();
  const file = new File(["audio"], "interview.mp3", { type: "audio/mpeg" });

  await uploadPresignedPost(
    { upload_url: "https://s3.example.test/bucket", fields: {} },
    file,
    { onProgress },
  );

  expect(onProgress).toHaveBeenNthCalledWith(1, 50);
  expect(onProgress).toHaveBeenLastCalledWith(100);
});

it("отменяет загрузку подписанной S3 POST-формы через AbortSignal", async () => {
  type Listener = (event: ProgressEvent) => void;
  const listeners = new Map<string, Listener>();

  class XMLHttpRequestMock {
    status = 0;
    upload = { addEventListener: vi.fn() };
    open = vi.fn();
    send = vi.fn();
    addEventListener(name: string, listener: Listener) {
      listeners.set(name, listener);
    }
    abort = vi.fn(() => listeners.get("abort")?.({} as ProgressEvent));
  }

  vi.stubGlobal("XMLHttpRequest", XMLHttpRequestMock);
  const controller = new AbortController();
  const file = new File(["video"], "interview.mp4", { type: "video/mp4" });
  const upload = uploadPresignedPost(
    { upload_url: "https://s3.example.test/bucket", fields: {} },
    file,
    { signal: controller.signal },
  );

  controller.abort();

  await expect(upload).rejects.toMatchObject({
    status: 0,
    code: "request_aborted",
    message: "Загрузка отменена",
  });
});

it("загружает multipart частями, ограничивает параллелизм и собирает ETag", async () => {
  type Listener = (event: ProgressEvent) => void;
  let activeRequests = 0;
  let maximumConcurrency = 0;

  class XMLHttpRequestMock {
    status = 200;
    private url = "";
    private listeners = new Map<string, Listener>();
    private uploadListeners = new Map<string, Listener>();
    upload = {
      addEventListener: (name: string, listener: Listener) =>
        this.uploadListeners.set(name, listener),
    };
    open(method: string, url: string) {
      expect(method).toBe("PUT");
      this.url = url;
    }
    setRequestHeader = vi.fn();
    getResponseHeader(name: string) {
      return name === "ETag" ? `"etag-${this.url.at(-1)}"` : null;
    }
    addEventListener(name: string, listener: Listener) {
      this.listeners.set(name, listener);
    }
    send = vi.fn((body: Blob) => {
      activeRequests += 1;
      maximumConcurrency = Math.max(maximumConcurrency, activeRequests);
      queueMicrotask(() => {
        this.uploadListeners.get("progress")?.({
          lengthComputable: true,
          loaded: body.size,
          total: body.size,
        } as ProgressEvent);
        activeRequests -= 1;
        this.listeners.get("load")?.({} as ProgressEvent);
      });
    });
    abort = vi.fn(() => this.listeners.get("abort")?.({} as ProgressEvent));
  }

  vi.stubGlobal("XMLHttpRequest", XMLHttpRequestMock);
  const onStatus = vi.fn();
  const file = new File(["abcdefgh"], "interview.mp4", {
    type: "video/mp4",
  });

  await expect(
    uploadStorageIntent(
      {
        upload_protocol: "multipart-v1",
        upload_id: "upload-id",
        upload_token: "upload-token",
        storage_key: "media/user/object",
        filename: file.name,
        content_type: file.type,
        size: file.size,
        part_size: 2,
        part_count: 4,
        parts: [1, 2, 3, 4].map((partNumber) => ({
          part_number: partNumber,
          upload_url: `https://s3.example.test/part-${partNumber}`,
          headers: { "x-test-header": "signed" },
        })),
        expires_in: 21_600,
        abort_url: "/api/v1/uploads/multipart/abort",
      },
      file,
      { onStatus },
    ),
  ).resolves.toEqual({
    upload_protocol: "multipart-v1",
    upload_id: "upload-id",
    upload_token: "upload-token",
    parts: [1, 2, 3, 4].map((partNumber) => ({
      part_number: partNumber,
      etag: `"etag-${partNumber}"`,
    })),
  });

  expect(maximumConcurrency).toBe(3);
  expect(onStatus).toHaveBeenLastCalledWith(
    expect.objectContaining({
      phase: "uploading",
      percent: 100,
      uploadedBytes: file.size,
    }),
  );
});

it("повторяет только неуспешную multipart-часть", async () => {
  type Listener = (event: ProgressEvent) => void;
  vi.useFakeTimers();
  let attempts = 0;

  class XMLHttpRequestMock {
    status = 0;
    private listeners = new Map<string, Listener>();
    upload = { addEventListener: vi.fn() };
    open = vi.fn();
    setRequestHeader = vi.fn();
    getResponseHeader = vi.fn(() => '"etag-after-retry"');
    addEventListener(name: string, listener: Listener) {
      this.listeners.set(name, listener);
    }
    send = vi.fn(() => {
      attempts += 1;
      this.status = attempts === 1 ? 500 : 200;
      queueMicrotask(() => this.listeners.get("load")?.({} as ProgressEvent));
    });
    abort = vi.fn(() => this.listeners.get("abort")?.({} as ProgressEvent));
  }
  vi.stubGlobal("XMLHttpRequest", XMLHttpRequestMock);
  const file = new File(["part"], "interview.mp4", { type: "video/mp4" });
  const upload = uploadStorageIntent(
    {
      upload_protocol: "multipart-v1",
      upload_id: "upload-id",
      upload_token: "upload-token",
      storage_key: "media/user/object",
      filename: file.name,
      content_type: file.type,
      size: file.size,
      part_size: file.size,
      part_count: 1,
      parts: [
        {
          part_number: 1,
          upload_url: "https://s3.example.test/part-1",
          headers: {},
        },
      ],
      expires_in: 21_600,
      abort_url: "/api/v1/uploads/multipart/abort",
    },
    file,
  );

  await vi.runAllTimersAsync();
  await expect(upload).resolves.toEqual(
    expect.objectContaining({
      parts: [{ part_number: 1, etag: '"etag-after-retry"' }],
    }),
  );
  expect(attempts).toBe(2);
});
