import { screen, waitFor } from "@testing-library/react";
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
import { renderPage } from "./render";

const media: ProtectedContentMediaRead = {
  id: "70000000-0000-4000-8000-000000000001",
  kind: "video",
  filename: "asyncio.mp4",
  content_type: "video/mp4",
  size: 1024,
  title: "Разбор asyncio",
  position: 3,
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
      signal: expect.any(AbortSignal),
    }),
  );

  await userEvent.click(screen.getByRole("button", { name: "Удалить" }));
  expect(remove).toHaveBeenCalledWith("topic-id", adminEntry.id, media.id);
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

it("лениво открывает защищённое видео статьи и обновляет ticket", async () => {
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
  expect(playback).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Открыть запись" }));
  const video = await screen.findByLabelText("Видео: Разбор asyncio");
  expect(playback).toHaveBeenCalledWith(entry.slug, media.id);
  expect(video).toHaveAttribute("controlsList", "nodownload noremoteplayback");
  expect(video).toHaveAttribute("disablePictureInPicture");
  await waitFor(() => expect(playback).toHaveBeenCalledTimes(2), {
    timeout: 1_600,
  });
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
  expect(playback).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Открыть запись" }));
  const player = await screen.findByLabelText(`Аудио: ${audio.title}`);
  expect(player).toHaveAttribute("controlsList", "nodownload noremoteplayback");
  expect(playback).toHaveBeenCalledWith(topic.id, audio.id);
});
