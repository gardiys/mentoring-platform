import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminKnowledgeEntryEditPage } from "../src/pages/AdminKnowledgeEntryEditPage";
import { AdminRoadmapTopicEditPage } from "../src/pages/AdminRoadmapTopicEditPage";
import { KnowledgeEntryPage } from "../src/pages/KnowledgeEntryPage";
import { TopicPage } from "../src/pages/TopicPage";
import type {
  AdminKnowledgeEntryRead,
  AdminTopicRead,
  KnowledgeEntryDetail,
  ProtectedContentMediaRead,
  TopicDetail,
} from "../src/types/api";
import { CONTENT_VIDEO_MAX_BYTES, VIDEO_MAX_BYTES } from "../src/utils/media";
import { renderPage } from "./render";

const media: ProtectedContentMediaRead = {
  id: "70000000-0000-4000-8000-000000000001",
  kind: "video",
  filename: "asyncio.mp4",
  content_type: "video/mp4",
  size: 1024,
  title: "Разбор asyncio",
  position: 3,
  processing_status: "ready",
  playback_available: true,
  normalization_attempts: 0,
  normalization_started_at: null,
  normalization_completed_at: null,
  normalization_error_code: null,
  normalization_error_message: null,
  created_at: "2026-08-04T10:00:00Z",
};

const adminEntry: AdminKnowledgeEntryRead = {
  id: "71000000-0000-4000-8000-000000000001",
  kind: "article",
  slug: "asyncio",
  title: "Asyncio",
  summary: null,
  content_markdown: "# Asyncio",
  position: 0,
  is_published: true,
  media: [media],
  updated_at: "2026-08-04T10:00:00Z",
};

const adminTopic: AdminTopicRead = {
  id: "72000000-0000-4000-8000-000000000001",
  slug: "goroutines",
  title: "Горутины",
  description: null,
  content_markdown: "# Горутины",
  position: 0,
  estimated_minutes: 30,
  is_published: true,
  media: [{ ...media, kind: "audio", content_type: "audio/mpeg" }],
};

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

it("загружает media через intent, presigned POST и finalize", async () => {
  const uploaded = { ...media, kind: "audio" as const };
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          upload_url: "https://s3.example.test/private",
          fields: { key: "pending/knowledge/audio.mp3", policy: "signed" },
          storage_key: "pending/knowledge/audio.mp3",
          filename: "audio.mp3",
          content_type: "audio/mpeg",
          size: 5,
          expires_in: 900,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    )
    .mockResolvedValueOnce(new Response(null, { status: 204 }))
    .mockResolvedValueOnce(
      new Response(JSON.stringify(uploaded), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
  const file = new File(["audio"], "audio.mp3", { type: "audio/mpeg" });

  await expect(
    api.uploadAdminKnowledgeMedia("topic-id", "entry-id", file, {
      title: "Лекция",
      position: 4,
    }),
  ).resolves.toEqual(uploaded);

  expect(String(fetchMock.mock.calls[0]?.[0])).toContain(
    "/api/v1/admin/knowledge/topics/topic-id/entries/entry-id/media/upload-url",
  );
  expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
    filename: "audio.mp3",
    content_type: "audio/mpeg",
    size: 5,
    upload_protocol: "multipart-v1",
  });
  expect(fetchMock.mock.calls[1]?.[0]).toBe("https://s3.example.test/private");
  const s3Body = fetchMock.mock.calls[1]?.[1]?.body as FormData;
  expect(s3Body.get("key")).toBe("pending/knowledge/audio.mp3");
  expect(s3Body.get("file")).toBe(file);
  expect(String(fetchMock.mock.calls[2]?.[0])).toContain(
    "/api/v1/admin/knowledge/topics/topic-id/entries/entry-id/media/finalize",
  );
  expect(JSON.parse(String(fetchMock.mock.calls[2]?.[1]?.body))).toEqual({
    filename: "audio.mp3",
    content_type: "audio/mpeg",
    size: 5,
    storage_key: "pending/knowledge/audio.mp3",
    title: "Лекция",
    position: 4,
  });
});

it("завершает multipart media с ETag и показывает фазу финализации", async () => {
  type Listener = (event: ProgressEvent) => void;
  const uploaded = { ...media, kind: "video" as const };
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          upload_protocol: "multipart-v1",
          upload_id: "upload-id",
          upload_token: "upload-token",
          storage_key: "knowledge-media/admin/object",
          filename: "lesson.mp4",
          content_type: "video/mp4",
          size: 5,
          part_size: 5,
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
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    )
    .mockResolvedValueOnce(
      new Response(JSON.stringify(uploaded), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );

  class XMLHttpRequestMock {
    status = 200;
    private listeners = new Map<string, Listener>();
    private uploadListeners = new Map<string, Listener>();
    upload = {
      addEventListener: (name: string, listener: Listener) =>
        this.uploadListeners.set(name, listener),
    };
    open = vi.fn();
    setRequestHeader = vi.fn();
    getResponseHeader = vi.fn((name: string) =>
      name === "ETag" ? '"part-etag"' : null,
    );
    addEventListener(name: string, listener: Listener) {
      this.listeners.set(name, listener);
    }
    send = vi.fn((body: Blob) => {
      this.uploadListeners.get("progress")?.({
        lengthComputable: true,
        loaded: body.size,
        total: body.size,
      } as ProgressEvent);
      this.listeners.get("load")?.({} as ProgressEvent);
    });
    abort = vi.fn(() => this.listeners.get("abort")?.({} as ProgressEvent));
  }
  vi.stubGlobal("XMLHttpRequest", XMLHttpRequestMock);
  const onStatus = vi.fn();
  const file = new File(["video"], "lesson.mp4", { type: "video/mp4" });

  await api.uploadAdminKnowledgeMedia(
    "topic-id",
    "entry-id",
    file,
    { title: "Лекция", position: 2 },
    { onStatus },
  );

  expect(JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body))).toEqual({
    filename: "lesson.mp4",
    content_type: "video/mp4",
    size: 5,
    upload_protocol: "multipart-v1",
  });
  expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
    filename: "lesson.mp4",
    content_type: "video/mp4",
    size: 5,
    title: "Лекция",
    position: 2,
    storage_key: "knowledge-media/admin/object",
    upload_protocol: "multipart-v1",
    upload_id: "upload-id",
    upload_token: "upload-token",
    parts: [{ part_number: 1, etag: '"part-etag"' }],
  });
  expect(onStatus.mock.calls.map(([status]) => status.phase)).toEqual(
    expect.arrayContaining(["preparing", "uploading", "finalizing"]),
  );
});

it("отменяет multipart-сессию в backend при отмене загрузки", async () => {
  const intent = {
    upload_protocol: "multipart-v1",
    upload_id: "upload-id",
    upload_token: "upload-token",
    storage_key: "knowledge-media/admin/object",
    filename: "lesson.mp4",
    content_type: "video/mp4",
    size: 5,
    part_size: 5,
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
  };
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(JSON.stringify(intent), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
    .mockResolvedValueOnce(new Response(null, { status: 204 }));
  const controller = new AbortController();
  const file = new File(["video"], "lesson.mp4", { type: "video/mp4" });
  const upload = api.uploadAdminKnowledgeMedia(
    "topic-id",
    "entry-id",
    file,
    { title: null, position: 0 },
    { signal: controller.signal },
  );

  controller.abort();

  await expect(upload).rejects.toMatchObject({ code: "request_aborted" });
  expect(String(fetchMock.mock.calls[1]?.[0])).toContain(
    "/api/v1/uploads/multipart/abort",
  );
  expect(JSON.parse(String(fetchMock.mock.calls[1]?.[1]?.body))).toEqual({
    upload_id: "upload-id",
    upload_token: "upload-token",
    storage_key: "knowledge-media/admin/object",
  });
});

it("повторяет только финализацию после 503, не загружая части заново", async () => {
  type Listener = (event: ProgressEvent) => void;
  vi.useFakeTimers();
  const uploaded = { ...media, kind: "video" as const };
  const intent = {
    upload_protocol: "multipart-v1",
    upload_id: "upload-id",
    upload_token: "upload-token",
    storage_key: "knowledge-media/admin/object",
    filename: "lesson.mp4",
    content_type: "video/mp4",
    size: 5,
    part_size: 5,
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
  };
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockResolvedValueOnce(
      new Response(JSON.stringify(intent), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    )
    .mockResolvedValueOnce(new Response(null, { status: 503 }))
    .mockResolvedValueOnce(
      new Response(JSON.stringify(uploaded), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      }),
    );
  let partUploads = 0;

  class XMLHttpRequestMock {
    status = 200;
    private listeners = new Map<string, Listener>();
    upload = { addEventListener: vi.fn() };
    open = vi.fn();
    setRequestHeader = vi.fn();
    getResponseHeader = vi.fn(() => '"part-etag"');
    addEventListener(name: string, listener: Listener) {
      this.listeners.set(name, listener);
    }
    send = vi.fn(() => {
      partUploads += 1;
      queueMicrotask(() => this.listeners.get("load")?.({} as ProgressEvent));
    });
    abort = vi.fn(() => this.listeners.get("abort")?.({} as ProgressEvent));
  }
  vi.stubGlobal("XMLHttpRequest", XMLHttpRequestMock);
  const file = new File(["video"], "lesson.mp4", { type: "video/mp4" });
  const upload = api.uploadAdminKnowledgeMedia("topic-id", "entry-id", file, {
    title: null,
    position: 0,
  });

  await vi.runAllTimersAsync();
  await expect(upload).resolves.toEqual(uploaded);
  expect(partUploads).toBe(1);
  expect(fetchMock).toHaveBeenCalledTimes(3);
  expect(
    fetchMock.mock.calls.some(([url]) =>
      String(url).includes("/multipart/abort"),
    ),
  ).toBe(false);
  expect(fetchMock.mock.calls[1]?.[1]?.body).toBe(
    fetchMock.mock.calls[2]?.[1]?.body,
  );
});

it("администратор видит, загружает и удаляет вложения статьи", async () => {
  vi.spyOn(api, "adminKnowledgeEntry").mockResolvedValue(adminEntry);
  const upload = vi
    .spyOn(api, "uploadAdminKnowledgeMedia")
    .mockReturnValue(new Promise(() => undefined));
  const remove = vi
    .spyOn(api, "deleteAdminKnowledgeMedia")
    .mockReturnValue(new Promise(() => undefined));
  vi.spyOn(window, "confirm").mockReturnValue(true);

  renderPage(
    <AdminKnowledgeEntryEditPage />,
    `/admin/knowledge/topic-id/entries/${adminEntry.id}/edit`,
    "/admin/knowledge/:topicId/entries/:entryId/edit",
  );

  expect(await screen.findByText("Разбор asyncio")).toBeInTheDocument();
  const fileInput =
    document.querySelector<HTMLInputElement>('input[type="file"]');
  expect(fileInput).not.toBeNull();
  const file = new File(["audio"], "lecture.mp3", { type: "audio/mpeg" });
  await userEvent.upload(fileInput!, file);
  await userEvent.type(
    screen.getByLabelText("Название для ученика"),
    "Лекция asyncio",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Загрузить медиа" }),
  );

  expect(upload).toHaveBeenCalledWith(
    "topic-id",
    adminEntry.id,
    file,
    { title: "Лекция asyncio", position: 4 },
    expect.objectContaining({
      onProgress: expect.any(Function),
      onStatus: expect.any(Function),
      signal: expect.any(AbortSignal),
    }),
  );

  await userEvent.click(screen.getByRole("button", { name: "Удалить" }));
  expect(remove).toHaveBeenCalledWith("topic-id", adminEntry.id, media.id);
});

it("администратор видит ошибку подготовки видео и может запустить её повторно", async () => {
  const failedMedia: ProtectedContentMediaRead = {
    ...media,
    processing_status: "failed",
    playback_available: false,
    normalization_error_code: "invalid_media",
    normalization_error_message: "Файл не является корректным видео.",
  };
  const entryRequest = vi
    .spyOn(api, "adminKnowledgeEntry")
    .mockResolvedValueOnce({
      ...adminEntry,
      media: [failedMedia],
    })
    .mockReturnValue(new Promise(() => undefined));
  const retry = vi
    .spyOn(api, "retryAdminContentMediaNormalization")
    .mockResolvedValue({
      ...failedMedia,
      processing_status: "queued",
      playback_available: false,
      normalization_error_code: null,
      normalization_error_message: null,
    });

  renderPage(
    <AdminKnowledgeEntryEditPage />,
    `/admin/knowledge/topic-id/entries/${adminEntry.id}/edit`,
    "/admin/knowledge/:topicId/entries/:entryId/edit",
  );

  expect(await screen.findByText("Ошибка подготовки")).toBeInTheDocument();
  expect(screen.getByText(/Код: invalid_media/)).toBeInTheDocument();
  expect(
    screen.getByText(/Файл не является корректным видео/),
  ).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Подготовить снова" }),
  );

  expect(retry).toHaveBeenCalledWith(media.id);
  expect(await screen.findByText("В очереди")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Подготовить снова" }),
  ).not.toBeInTheDocument();
  expect(entryRequest.mock.calls.length).toBeGreaterThanOrEqual(2);
});

it("разрешает учебное видео больше 2 ГБ в пределах нового лимита 5 ГБ", async () => {
  vi.spyOn(api, "adminKnowledgeEntry").mockResolvedValue({
    ...adminEntry,
    media: [],
  });
  const upload = vi
    .spyOn(api, "uploadAdminKnowledgeMedia")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <AdminKnowledgeEntryEditPage />,
    `/admin/knowledge/topic-id/entries/${adminEntry.id}/edit`,
    "/admin/knowledge/:topicId/entries/:entryId/edit",
  );

  expect(
    await screen.findByText(/Видео — до 5 ГБ, аудио — до 500 МБ/),
  ).toBeInTheDocument();
  const fileInput =
    document.querySelector<HTMLInputElement>('input[type="file"]');
  expect(fileInput).not.toBeNull();
  const file = new File(["video"], "long-lesson.mp4", { type: "video/mp4" });
  Object.defineProperty(file, "size", { value: VIDEO_MAX_BYTES + 1 });
  expect(file.size).toBeLessThanOrEqual(CONTENT_VIDEO_MAX_BYTES);

  await userEvent.upload(fileInput!, file);
  await userEvent.click(
    screen.getByRole("button", { name: "Загрузить медиа" }),
  );

  expect(upload).toHaveBeenCalledWith(
    "topic-id",
    adminEntry.id,
    file,
    { title: null, position: 0 },
    expect.objectContaining({
      onProgress: expect.any(Function),
      onStatus: expect.any(Function),
      signal: expect.any(AbortSignal),
    }),
  );
});

it("разрешает MOV и передаёт его на автоматическую подготовку", async () => {
  vi.spyOn(api, "adminKnowledgeEntry").mockResolvedValue({
    ...adminEntry,
    media: [],
  });
  const upload = vi
    .spyOn(api, "uploadAdminKnowledgeMedia")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <AdminKnowledgeEntryEditPage />,
    `/admin/knowledge/topic-id/entries/${adminEntry.id}/edit`,
    "/admin/knowledge/:topicId/entries/:entryId/edit",
  );

  await screen.findByText("Вложений пока нет.");
  const fileInput =
    document.querySelector<HTMLInputElement>('input[type="file"]');
  expect(fileInput).not.toBeNull();
  const file = new File(["video"], "lesson.mov", {
    type: "video/quicktime",
  });
  await userEvent.upload(fileInput!, file);
  await userEvent.click(
    screen.getByRole("button", { name: "Загрузить медиа" }),
  );

  expect(upload).toHaveBeenCalledWith(
    "topic-id",
    adminEntry.id,
    file,
    { title: null, position: 0 },
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
});

it("не отправляет неподдерживаемый или пустой media-файл", async () => {
  vi.spyOn(api, "adminKnowledgeEntry").mockResolvedValue({
    ...adminEntry,
    media: [],
  });
  const upload = vi
    .spyOn(api, "uploadAdminKnowledgeMedia")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <AdminKnowledgeEntryEditPage />,
    `/admin/knowledge/topic-id/entries/${adminEntry.id}/edit`,
    "/admin/knowledge/:topicId/entries/:entryId/edit",
  );
  await screen.findByText("Вложений пока нет.");
  const fileInput =
    document.querySelector<HTMLInputElement>('input[type="file"]');
  expect(fileInput).not.toBeNull();
  expect(fileInput!.accept).toContain("video/mp4");
  expect(fileInput!.accept).toContain("video/quicktime");
  expect(fileInput!.accept).not.toContain("video/webm");
  expect(fileInput!.accept).not.toContain("video/x-matroska");

  for (const unsupported of [
    new File(["video"], "archive.mkv", { type: "video/x-matroska" }),
    new File(["video"], "browser.webm", { type: "video/webm" }),
  ]) {
    await userEvent.upload(fileInput!, unsupported, { applyAccept: false });
    await userEvent.click(
      screen.getByRole("button", { name: "Загрузить медиа" }),
    );
  }
  expect(upload).not.toHaveBeenCalled();

  await userEvent.upload(
    fileInput!,
    new File(["video"], "legacy.avi", { type: "video/x-msvideo" }),
    { applyAccept: false },
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Загрузить медиа" }),
  );
  expect(upload).not.toHaveBeenCalled();

  await userEvent.upload(
    fileInput!,
    new File([], "empty.mp4", { type: "video/mp4" }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Загрузить медиа" }),
  );
  expect(upload).not.toHaveBeenCalled();

  const oversizedVideo = new File(["video"], "too-large.mp4", {
    type: "video/mp4",
  });
  Object.defineProperty(oversizedVideo, "size", {
    value: CONTENT_VIDEO_MAX_BYTES + 1,
  });
  await userEvent.upload(fileInput!, oversizedVideo);
  await userEvent.click(
    screen.getByRole("button", { name: "Загрузить медиа" }),
  );
  expect(upload).not.toHaveBeenCalled();
});

it("для новой темы роадмапа объясняет, почему загрузка пока недоступна", async () => {
  renderPage(
    <AdminRoadmapTopicEditPage />,
    "/admin/roadmaps/roadmap-id/sections/section-id/topics/new",
    "/admin/roadmaps/:roadmapId/sections/:sectionId/topics/new",
  );

  expect(
    await screen.findByText(/Создайте тему, затем снова откройте её/),
  ).toBeInTheDocument();
  expect(
    screen.queryByLabelText("Аудио- или видеофайл"),
  ).not.toBeInTheDocument();
});

it("редактор темы роадмапа показывает существующие media", async () => {
  vi.spyOn(api, "adminRoadmapTopic").mockResolvedValue(adminTopic);
  renderPage(
    <AdminRoadmapTopicEditPage />,
    `/admin/roadmaps/roadmap-id/sections/section-id/topics/${adminTopic.id}/edit`,
    "/admin/roadmaps/:roadmapId/sections/:sectionId/topics/:topicId/edit",
  );

  expect(await screen.findByText("Разбор asyncio")).toBeInTheDocument();
  expect(screen.getByText("Аудио")).toBeInTheDocument();
});

it("редактор темы роадмапа безопасно изменяет и сохраняет материал", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "adminRoadmapTopic").mockResolvedValue(adminTopic);
  const update = vi.spyOn(api, "updateAdminRoadmapTopic").mockResolvedValue({
    ...adminTopic,
    title: "Конкурентность в Go",
    content_markdown: "# Конкурентность в Go",
  });
  renderPage(
    <AdminRoadmapTopicEditPage />,
    `/admin/roadmaps/roadmap-id/sections/section-id/topics/${adminTopic.id}/edit`,
    "/admin/roadmaps/:roadmapId/sections/:sectionId/topics/:topicId/edit",
  );

  const title = await screen.findByRole("textbox", { name: "Название" });
  await user.clear(title);
  await user.type(title, "Конкурентность в Go");
  const content = screen.getByRole("textbox", {
    name: "Содержание (Markdown)",
  });
  await user.clear(content);
  await user.type(content, "# Конкурентность в Go");
  await user.click(screen.getByRole("button", { name: "Сохранить" }));

  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(
      "roadmap-id",
      "section-id",
      adminTopic.id,
      expect.objectContaining({
        title: "Конкурентность в Go",
        content_markdown: "# Конкурентность в Go",
      }),
    ),
  );
});

it("показывает видео статьи перед текстом и обновляет ticket", async () => {
  const entry: KnowledgeEntryDetail = {
    id: adminEntry.id,
    kind: adminEntry.kind,
    slug: adminEntry.slug,
    title: adminEntry.title,
    summary: adminEntry.summary,
    content_markdown: adminEntry.content_markdown,
    topic: { id: "topic-id", slug: "python", title: "Python" },
    media: [media],
    updated_at: adminEntry.updated_at,
  };
  vi.spyOn(api, "knowledgeEntry").mockResolvedValue(entry);
  const playback = vi.spyOn(api, "knowledgeMediaPlayback").mockResolvedValue({
    url: "http://localhost:8000/api/v1/knowledge/stream",
    expires_in: 1,
  });

  renderPage(
    <KnowledgeEntryPage />,
    `/knowledge/entries/${entry.slug}`,
    "/knowledge/entries/:entrySlug",
  );

  expect(await screen.findByText("Разбор asyncio")).toBeInTheDocument();
  const video = (await screen.findByLabelText(
    "Видео: Разбор asyncio",
  )) as HTMLVideoElement;
  const mediaHeading = screen.getByRole("heading", { name: "Аудио и видео" });
  const articleHeading = screen
    .getAllByRole("heading", { name: "Asyncio" })
    .at(-1);
  expect(articleHeading).toBeDefined();
  expect(
    mediaHeading.compareDocumentPosition(articleHeading as HTMLElement) &
      Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(playback).toHaveBeenCalledWith(entry.slug, media.id);
  expect(
    screen.getByRole("button", { name: "Скрыть запись" }),
  ).toBeInTheDocument();
  expect(video).toHaveAttribute("controlsList", "nodownload noremoteplayback");
  expect(video).toHaveAttribute("disablePictureInPicture");
  expect(video).toHaveAttribute("preload", "metadata");
  Object.defineProperty(video, "currentTime", {
    configurable: true,
    value: 42,
    writable: true,
  });
  await waitFor(() => expect(playback).toHaveBeenCalledTimes(2), {
    timeout: 1_600,
  });
  const renewedVideo = (await screen.findByLabelText(
    "Видео: Разбор asyncio",
  )) as HTMLVideoElement;
  expect(renewedVideo).not.toBe(video);
  Object.defineProperty(renewedVideo, "duration", {
    configurable: true,
    value: 120,
  });
  fireEvent.loadedMetadata(renewedVideo);
  expect(renewedVideo.currentTime).toBe(42);
});

it("сохраняет воспроизведение legacy media без полей нового контракта", async () => {
  const legacyMedia = { ...media } as unknown as Record<string, unknown>;
  delete legacyMedia.processing_status;
  delete legacyMedia.playback_available;
  const entry: KnowledgeEntryDetail = {
    id: adminEntry.id,
    kind: adminEntry.kind,
    slug: adminEntry.slug,
    title: adminEntry.title,
    summary: adminEntry.summary,
    content_markdown: adminEntry.content_markdown,
    topic: { id: "topic-id", slug: "python", title: "Python" },
    media: [legacyMedia as unknown as ProtectedContentMediaRead],
    updated_at: adminEntry.updated_at,
  };
  vi.spyOn(api, "knowledgeEntry").mockResolvedValue(entry);
  const playback = vi.spyOn(api, "knowledgeMediaPlayback").mockResolvedValue({
    url: "http://localhost:8000/api/v1/knowledge/legacy-stream",
    expires_in: 600,
  });

  renderPage(
    <KnowledgeEntryPage />,
    `/knowledge/entries/${entry.slug}`,
    "/knowledge/entries/:entrySlug",
  );

  expect(
    await screen.findByLabelText("Видео: Разбор asyncio"),
  ).toBeInTheDocument();
  expect(playback).toHaveBeenCalledWith(entry.slug, media.id);
});

it("не падает и не открывает media с неизвестным будущим статусом", async () => {
  const unknownMedia = {
    ...media,
    processing_status: "future_processing_state",
  } as unknown as Record<string, unknown>;
  delete unknownMedia.playback_available;
  const entry: KnowledgeEntryDetail = {
    id: adminEntry.id,
    kind: adminEntry.kind,
    slug: adminEntry.slug,
    title: adminEntry.title,
    summary: adminEntry.summary,
    content_markdown: adminEntry.content_markdown,
    topic: { id: "topic-id", slug: "python", title: "Python" },
    media: [unknownMedia as unknown as ProtectedContentMediaRead],
    updated_at: adminEntry.updated_at,
  };
  vi.spyOn(api, "knowledgeEntry").mockResolvedValue(entry);
  const playback = vi.spyOn(api, "knowledgeMediaPlayback");

  renderPage(
    <KnowledgeEntryPage />,
    `/knowledge/entries/${entry.slug}`,
    "/knowledge/entries/:entrySlug",
  );

  expect((await screen.findAllByText("Временно недоступно")).length).toBe(2);
  expect(
    screen.getByRole("button", { name: "Временно недоступно" }),
  ).toBeDisabled();
  expect(playback).not.toHaveBeenCalled();
});

it("показывает статус подготовки, но разрешает открыть legacy-оригинал", async () => {
  const queuedLegacyMedia: ProtectedContentMediaRead = {
    ...media,
    processing_status: "queued",
    playback_available: true,
  };
  const entry: KnowledgeEntryDetail = {
    id: adminEntry.id,
    kind: adminEntry.kind,
    slug: adminEntry.slug,
    title: adminEntry.title,
    summary: adminEntry.summary,
    content_markdown: adminEntry.content_markdown,
    topic: { id: "topic-id", slug: "python", title: "Python" },
    media: [queuedLegacyMedia],
    updated_at: adminEntry.updated_at,
  };
  vi.spyOn(api, "knowledgeEntry").mockResolvedValue(entry);
  const playback = vi.spyOn(api, "knowledgeMediaPlayback").mockResolvedValue({
    url: "http://localhost:8000/api/v1/knowledge/original-stream",
    expires_in: 600,
  });

  renderPage(
    <KnowledgeEntryPage />,
    `/knowledge/entries/${entry.slug}`,
    "/knowledge/entries/:entrySlug",
  );

  expect(await screen.findByText("Ожидает подготовки")).toBeInTheDocument();
  expect(
    screen.getByText(/можно смотреть исходную запись/),
  ).toBeInTheDocument();
  expect(
    await screen.findByLabelText("Видео: Разбор asyncio"),
  ).toBeInTheDocument();
  expect(playback).toHaveBeenCalledWith(entry.slug, media.id);
});

it("не открывает видео статьи, пока платформа подготавливает его", async () => {
  const queuedMedia: ProtectedContentMediaRead = {
    ...media,
    processing_status: "queued",
    playback_available: false,
  };
  const entry: KnowledgeEntryDetail = {
    id: adminEntry.id,
    kind: adminEntry.kind,
    slug: adminEntry.slug,
    title: adminEntry.title,
    summary: adminEntry.summary,
    content_markdown: adminEntry.content_markdown,
    topic: { id: "topic-id", slug: "python", title: "Python" },
    media: [queuedMedia],
    updated_at: adminEntry.updated_at,
  };
  vi.spyOn(api, "knowledgeEntry").mockResolvedValue(entry);
  const playback = vi.spyOn(api, "knowledgeMediaPlayback");

  renderPage(
    <KnowledgeEntryPage />,
    `/knowledge/entries/${entry.slug}`,
    "/knowledge/entries/:entrySlug",
  );

  expect((await screen.findAllByText("Ожидает подготовки")).length).toBe(2);
  expect(
    screen.getByText(/Видео ожидает подготовки для быстрой загрузки/),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "Ожидает подготовки" }),
  ).toBeDisabled();
  expect(playback).not.toHaveBeenCalled();
});

it("показывает ученику понятный статус при ошибке подготовки видео", async () => {
  const failedMedia: ProtectedContentMediaRead = {
    ...media,
    processing_status: "failed",
    playback_available: false,
    normalization_error_code: "normalization_failed",
    normalization_error_message: "Внутренняя ошибка подготовки.",
  };
  const entry: KnowledgeEntryDetail = {
    id: adminEntry.id,
    kind: adminEntry.kind,
    slug: adminEntry.slug,
    title: adminEntry.title,
    summary: adminEntry.summary,
    content_markdown: adminEntry.content_markdown,
    topic: { id: "topic-id", slug: "python", title: "Python" },
    media: [failedMedia],
    updated_at: adminEntry.updated_at,
  };
  vi.spyOn(api, "knowledgeEntry").mockResolvedValue(entry);

  renderPage(
    <KnowledgeEntryPage />,
    `/knowledge/entries/${entry.slug}`,
    "/knowledge/entries/:entrySlug",
  );

  expect((await screen.findAllByText("Временно недоступно")).length).toBe(2);
  expect(
    screen.getByText(/Администратор может запустить подготовку повторно/),
  ).toBeInTheDocument();
  expect(screen.queryByText(/normalization_failed/)).not.toBeInTheDocument();
});

it("один раз автоматически обновляет доступ при сбое видео", async () => {
  const entry: KnowledgeEntryDetail = {
    id: adminEntry.id,
    kind: adminEntry.kind,
    slug: adminEntry.slug,
    title: adminEntry.title,
    summary: adminEntry.summary,
    content_markdown: adminEntry.content_markdown,
    topic: { id: "topic-id", slug: "python", title: "Python" },
    media: [media],
    updated_at: adminEntry.updated_at,
  };
  vi.spyOn(api, "knowledgeEntry").mockResolvedValue(entry);
  const playback = vi.spyOn(api, "knowledgeMediaPlayback").mockResolvedValue({
    url: "http://localhost:8000/api/v1/knowledge/stream",
    expires_in: 600,
  });

  renderPage(
    <KnowledgeEntryPage />,
    `/knowledge/entries/${entry.slug}`,
    "/knowledge/entries/:entrySlug",
  );

  const firstPlayer = await screen.findByLabelText("Видео: Разбор asyncio");
  fireEvent.error(firstPlayer);

  await waitFor(() => expect(playback).toHaveBeenCalledTimes(2));
  const renewedPlayer = await screen.findByLabelText("Видео: Разбор asyncio");
  expect(renewedPlayer).not.toBe(firstPlayer);
  fireEvent.error(renewedPlayer);
  expect(
    await screen.findByText("Запись не удалось воспроизвести"),
  ).toBeInTheDocument();
});

it("открывает защищённое аудио в теме роадмапа", async () => {
  const audio = {
    ...media,
    kind: "audio" as const,
    filename: "goroutines.mp3",
    content_type: "audio/mpeg",
    title: "Горутины: аудиолекция",
  };
  const topic: TopicDetail = {
    id: adminTopic.id,
    slug: adminTopic.slug,
    title: adminTopic.title,
    description: null,
    content_markdown: adminTopic.content_markdown,
    estimated_minutes: 30,
    media: [audio],
    roadmap: { id: "roadmap-id", slug: "go", title: "Go" },
    section: { id: "section-id", title: "Основы" },
    status: "not_started",
    started_at: null,
    first_completed_at: null,
    last_completed_at: null,
  };
  vi.spyOn(api, "topic").mockResolvedValue(topic);
  const playback = vi
    .spyOn(api, "roadmapTopicMediaPlayback")
    .mockResolvedValue({
      url: "http://localhost:8000/api/v1/topics/stream",
      expires_in: 600,
    });

  renderPage(<TopicPage />, `/topics/${topic.id}`, "/topics/:topicId");

  expect(await screen.findByText(audio.title)).toBeInTheDocument();
  const player = await screen.findByLabelText(`Аудио: ${audio.title}`);
  const mediaHeading = screen.getByRole("heading", { name: "Аудио и видео" });
  const materialHeading = screen
    .getAllByRole("heading", { name: "Горутины" })
    .at(-1);
  expect(materialHeading).toBeDefined();
  expect(
    mediaHeading.compareDocumentPosition(materialHeading as HTMLElement) &
      Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy();
  expect(player).toHaveAttribute("controlsList", "nodownload noremoteplayback");
  expect(player).toHaveAttribute("preload", "metadata");
  expect(playback).toHaveBeenCalledWith(topic.id, audio.id);
});
