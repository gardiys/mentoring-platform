import { notifications } from "@mantine/notifications";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { ContentMarkdown } from "../src/components/ContentMarkdown";
import { ProtectedContentMediaList } from "../src/components/ProtectedContentMediaList";
import { AdminKnowledgeEntryEditPage } from "../src/pages/AdminKnowledgeEntryEditPage";
import { AdminRoadmapTopicEditPage } from "../src/pages/AdminRoadmapTopicEditPage";
import type {
  AdminKnowledgeEntryRead,
  ProtectedContentMediaRead,
} from "../src/types/api";
import { contentImageSource } from "../src/utils/contentImages";
import { renderPage } from "./render";

const image: ProtectedContentMediaRead = {
  id: "70000000-0000-4000-8000-000000000002",
  kind: "image",
  filename: "diagram.png",
  content_type: "image/png",
  size: 8,
  title: null,
  position: 0,
  processing_status: "ready",
  playback_available: true,
  normalization_attempts: 0,
  normalization_started_at: null,
  normalization_completed_at: null,
  normalization_error_code: null,
  normalization_error_message: null,
  created_at: "2026-10-07T10:00:00Z",
};
const entry: AdminKnowledgeEntryRead = {
  id: "71000000-0000-4000-8000-000000000001",
  kind: "article",
  slug: "images",
  title: "Изображения",
  summary: null,
  content_markdown: "До\n\nПосле",
  position: 0,
  is_published: true,
  media: [],
  updated_at: "2026-10-07T10:00:00Z",
};

afterEach(() => {
  vi.restoreAllMocks();
});

async function renderEntry() {
  vi.spyOn(api, "adminKnowledgeEntry").mockResolvedValue(entry);
  const page = renderPage(
    <AdminKnowledgeEntryEditPage />,
    "/admin/knowledge/topic-id/entries/entry-id/edit",
    "/admin/knowledge/:topicId/entries/:entryId/edit",
  );
  await screen.findByLabelText(/Содержание \(Markdown\)/);
  return page;
}

it("вставляет изображение из буфера в позицию курсора и загружает при сохранении", async () => {
  const user = userEvent.setup();
  const upload = vi
    .spyOn(api, "uploadAdminKnowledgeMedia")
    .mockResolvedValue(image);
  const save = vi
    .spyOn(api, "updateAdminKnowledgeEntry")
    .mockResolvedValue(entry);
  await renderEntry();
  const textarea = screen.getByLabelText(
    /Содержание \(Markdown\)/,
  ) as HTMLTextAreaElement;
  textarea.focus();
  textarea.setSelectionRange(2, 2);
  const file = new File(["png-data"], "diagram.png", { type: "image/png" });
  fireEvent.paste(textarea, {
    clipboardData: {
      items: [{ kind: "file", type: "image/png", getAsFile: () => file }],
      files: [file],
    },
  });
  expect(textarea.value).toMatch(
    /^До\n\n!\[diagram.png\]\(\/content-images\/pending\/[a-f0-9-]+\)\n\nПосле$/,
  );
  expect(upload).not.toHaveBeenCalled();
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() => expect(save).toHaveBeenCalled());
  expect(upload).toHaveBeenCalledWith(
    "topic-id",
    entry.id,
    file,
    { title: null, position: 0 },
    expect.objectContaining({ signal: expect.any(AbortSignal) }),
  );
  expect(save.mock.calls[0]?.[2].content_markdown).toBe(
    `До\n\n![diagram.png](${contentImageSource(image.id)})\n\nПосле`,
  );
});

it("загружает файл в новую статью и публикует только после успешного добавления картинки", async () => {
  const user = userEvent.setup();
  const create = vi
    .spyOn(api, "createAdminKnowledgeEntry")
    .mockResolvedValue({ ...entry, is_published: false });
  const upload = vi
    .spyOn(api, "uploadAdminKnowledgeMedia")
    .mockResolvedValue(image);
  const save = vi
    .spyOn(api, "updateAdminKnowledgeEntry")
    .mockResolvedValue(entry);
  renderPage(
    <AdminKnowledgeEntryEditPage />,
    "/admin/knowledge/topic-id/entries/new",
    "/admin/knowledge/:topicId/entries/new",
  );
  fireEvent.change(screen.getByLabelText("Название", { exact: false }), {
    target: { value: "Новая статья" },
  });
  fireEvent.change(screen.getByLabelText("Slug", { exact: false }), {
    target: { value: "new-article" },
  });
  await user.click(screen.getByLabelText("Опубликован"));
  const file = new File(["png-data"], "diagram.png", { type: "image/png" });
  await user.upload(screen.getByLabelText("Выбрать изображения"), file);
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() => expect(save).toHaveBeenCalled());
  expect(create).toHaveBeenCalledTimes(1);
  expect(create.mock.calls[0]?.[1].is_published).toBe(false);
  expect(create.mock.calls[0]?.[1].content_markdown).not.toContain("/pending/");
  expect(upload).toHaveBeenCalledTimes(1);
  expect(save.mock.calls[0]?.[2]).toMatchObject({ is_published: true });
  expect(save.mock.calls[0]?.[2].content_markdown).toContain(
    contentImageSource(image.id),
  );
});

it("после ошибки сохранения переиспользует загруженное изображение", async () => {
  const user = userEvent.setup();
  const upload = vi
    .spyOn(api, "uploadAdminKnowledgeMedia")
    .mockResolvedValue(image);
  const save = vi
    .spyOn(api, "updateAdminKnowledgeEntry")
    .mockRejectedValueOnce(new Error("Не сохранено"))
    .mockResolvedValue(entry);
  vi.spyOn(notifications, "show");
  await renderEntry();
  await user.upload(
    screen.getByLabelText("Выбрать изображения"),
    new File(["png-data"], "diagram.png", { type: "image/png" }),
  );
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() =>
    expect(notifications.show).toHaveBeenCalledWith(
      expect.objectContaining({ message: "Не сохранено" }),
    ),
  );
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Сохранить" })).toBeEnabled(),
  );
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
  expect(upload).toHaveBeenCalledTimes(1);
});

it("не загружает изображение, удалённое из текста до сохранения", async () => {
  const user = userEvent.setup();
  const upload = vi
    .spyOn(api, "uploadAdminKnowledgeMedia")
    .mockResolvedValue(image);
  const save = vi
    .spyOn(api, "updateAdminKnowledgeEntry")
    .mockResolvedValue(entry);
  await renderEntry();
  await user.upload(
    screen.getByLabelText("Выбрать изображения"),
    new File(["png-data"], "diagram.png", { type: "image/png" }),
  );
  fireEvent.change(screen.getByLabelText(/Содержание \(Markdown\)/), {
    target: { value: "Только текст" },
  });
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() => expect(save).toHaveBeenCalled());
  expect(upload).not.toHaveBeenCalled();
  expect(save.mock.calls[0]?.[2].content_markdown).toBe("Только текст");
});

it("обычная вставка текста не перехватывается, SVG из буфера отклоняется", async () => {
  vi.spyOn(notifications, "show");
  await renderEntry();
  const textarea = screen.getByLabelText(/Содержание \(Markdown\)/);
  expect(
    fireEvent.paste(textarea, { clipboardData: { items: [], files: [] } }),
  ).toBe(true);
  const file = new File(["<svg/>"], "image.svg", { type: "image/svg+xml" });
  fireEvent.paste(textarea, {
    clipboardData: {
      items: [{ kind: "file", type: "image/svg+xml", getAsFile: () => file }],
      files: [file],
    },
  });
  expect(textarea).toHaveValue(entry.content_markdown);
  expect(notifications.show).toHaveBeenCalledWith(
    expect.objectContaining({ color: "red" }),
  );
});

it("сохраняет картинку внутри темы роадмапа", async () => {
  const user = userEvent.setup();
  const topic = {
    id: entry.id,
    slug: "topic",
    title: "Тема",
    description: null,
    content_markdown: "Текст",
    position: 0,
    estimated_minutes: null,
    is_published: true,
    media: [],
  };
  vi.spyOn(api, "adminRoadmapTopic").mockResolvedValue(topic);
  const upload = vi
    .spyOn(api, "uploadAdminRoadmapTopicMedia")
    .mockResolvedValue(image);
  const save = vi
    .spyOn(api, "updateAdminRoadmapTopic")
    .mockResolvedValue(topic);
  renderPage(
    <AdminRoadmapTopicEditPage />,
    "/admin/roadmaps/r/sections/s/topics/t/edit",
    "/admin/roadmaps/:roadmapId/sections/:sectionId/topics/:topicId/edit",
  );
  await screen.findByLabelText(/Содержание \(Markdown\)/);
  await user.upload(
    screen.getByLabelText("Выбрать изображения"),
    new File(["png-data"], "diagram.png", { type: "image/png" }),
  );
  await user.click(screen.getByRole("button", { name: "Сохранить" }));
  await waitFor(() => expect(save).toHaveBeenCalled());
  expect(upload.mock.calls[0]?.slice(0, 3)).toEqual(["r", "s", entry.id]);
  expect(save.mock.calls[0]?.[3].content_markdown).toContain(
    contentImageSource(image.id),
  );
});

it("показывает приватную картинку внутри Markdown и обновляет истёкший доступ", async () => {
  const load = vi
    .fn()
    .mockResolvedValue({ url: "/private-image/stream", expires_in: 600 });
  renderPage(
    <ContentMarkdown
      media={[image]}
      resourceKey="article:test"
      loadPlayback={load}
    >{`До\n\n![Схема](${contentImageSource(image.id)})\n\nПосле`}</ContentMarkdown>,
  );
  const rendered = await screen.findByAltText("Схема");
  expect(rendered.tagName).toBe("IMG");
  expect(rendered.getAttribute("src")).toContain("/private-image/stream");
  expect(load).toHaveBeenCalledWith(image.id);
  fireEvent.error(rendered);
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  const renewed = screen.getByAltText("Схема");
  fireEvent.error(renewed);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Не удалось загрузить изображение",
  );
});

it("не запрашивает изображение другого материала и не превращает картинки в аудиоплеер", () => {
  const load = vi.fn();
  renderPage(
    <>
      <ContentMarkdown
        media={[]}
        resourceKey="article:test"
        loadPlayback={load}
      >{`![Чужое](${contentImageSource(image.id)})`}</ContentMarkdown>
      <ProtectedContentMediaList
        media={[image]}
        resourceKey="article:test"
        loadPlayback={load}
      />
    </>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Изображение недоступно");
  expect(load).not.toHaveBeenCalled();
  expect(document.querySelector("audio, video")).toBeNull();
});
