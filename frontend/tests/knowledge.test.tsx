import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminKnowledgeTopicForm } from "../src/features/admin/AdminKnowledgeTopicForm";
import { KnowledgeBasePage } from "../src/pages/KnowledgeBasePage";
import { KnowledgeEntryPage } from "../src/pages/KnowledgeEntryPage";
import type {
  KnowledgeEntryDetail,
  KnowledgeSearchResult,
  KnowledgeTopicListItem,
} from "../src/types/api";
import { renderPage } from "./render";

const topic: KnowledgeTopicListItem = {
  id: "50000000-0000-4000-8000-000000000001",
  slug: "backend-foundations",
  title: "Основы Backend",
  description: "Базовые концепции",
  article_count: 2,
  question_count: 3,
};

const searchResult: KnowledgeSearchResult = {
  id: "51000000-0000-4000-8000-000000000001",
  kind: "question",
  slug: "event-loop",
  title: "Как работает event loop?",
  summary: "Вопрос про асинхронность",
  topic: { id: topic.id, slug: topic.slug, title: topic.title },
  excerpt: "Event loop планирует корутины и переключается между ними.",
  rank: 0.8,
};

const entry: KnowledgeEntryDetail = {
  id: searchResult.id,
  kind: "question",
  slug: searchResult.slug,
  title: searchResult.title,
  summary: searchResult.summary,
  content_markdown: "# Краткий ответ\n\nИспользуйте `await` для ожидания.",
  topic: searchResult.topic,
  updated_at: "2026-07-31T12:00:00Z",
};

afterEach(() => vi.restoreAllMocks());

it("показывает темы, статьи и вопросы базы знаний", async () => {
  vi.spyOn(api, "knowledgeTopics").mockResolvedValue([topic]);
  renderPage(<KnowledgeBasePage />, "/knowledge", "/knowledge");

  expect(await screen.findByText("Основы Backend")).toBeInTheDocument();
  expect(screen.getByText("2 статей")).toBeInTheDocument();
  expect(screen.getByText("3 вопросов")).toBeInTheDocument();
});

it("показывает результаты полнотекстового поиска", async () => {
  vi.spyOn(api, "knowledgeTopics").mockResolvedValue([topic]);
  const search = vi
    .spyOn(api, "knowledgeSearch")
    .mockResolvedValue([searchResult]);
  renderPage(<KnowledgeBasePage />, "/knowledge?q=асинхронность", "/knowledge");

  expect(
    await screen.findByText("Как работает event loop?"),
  ).toBeInTheDocument();
  expect(screen.getByText(/планирует корутины/)).toBeInTheDocument();
  expect(search).toHaveBeenCalledWith("асинхронность");
});

it("рендерит Markdown материала", async () => {
  vi.spyOn(api, "knowledgeEntry").mockResolvedValue(entry);
  renderPage(
    <KnowledgeEntryPage />,
    "/knowledge/entries/event-loop",
    "/knowledge/entries/:entrySlug",
  );

  expect(
    await screen.findByRole("heading", { name: "Краткий ответ" }),
  ).toBeInTheDocument();
  expect(screen.getByText("await")).toBeInTheDocument();
});

it("администратор создаёт тему с вопросом", async () => {
  vi.spyOn(api, "adminStudentOptions").mockResolvedValue({
    tracks: [
      {
        id: "30000000-0000-4000-8000-000000000001",
        slug: "python",
        title: "Python",
        is_published: true,
      },
    ],
    mentors: [],
  });
  const create = vi
    .spyOn(api, "createAdminKnowledgeTopic")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<AdminKnowledgeTopicForm />);

  await userEvent.type(
    screen.getByLabelText(/^Название темы/),
    "Собеседования",
  );
  await userEvent.type(screen.getByLabelText(/^Slug темы/), "interview");
  await userEvent.click(screen.getByRole("textbox", { name: "Направления" }));
  await userEvent.keyboard("{ArrowDown}{Enter}");
  await userEvent.click(screen.getByRole("button", { name: "+ Вопрос" }));
  await userEvent.type(
    screen.getByLabelText(/^Заголовок/),
    "Что такое индекс?",
  );
  await userEvent.type(
    screen.getByLabelText(/^Slug материала/),
    "database-index",
  );
  await userEvent.click(screen.getByRole("button", { name: "Создать тему" }));

  expect(create).toHaveBeenCalledWith(
    expect.objectContaining({
      slug: "interview",
      entries: [
        expect.objectContaining({
          kind: "question",
          slug: "database-index",
          title: "Что такое индекс?",
        }),
      ],
    }),
  );
});
