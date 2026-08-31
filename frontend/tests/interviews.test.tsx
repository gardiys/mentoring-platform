import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminInterviewDeckForm } from "../src/features/admin/AdminInterviewDeckForm";
import { AdminInterviewCardEditPage } from "../src/pages/AdminInterviewCardEditPage";
import { InterviewQuestionsPage } from "../src/pages/InterviewQuestionsPage";
import { InterviewStudyPage } from "../src/pages/InterviewStudyPage";
import { InterviewsPage } from "../src/pages/InterviewsPage";
import type {
  AdminInterviewDeckRead,
  AdminInterviewCardRead,
  AdminTrackRead,
  InterviewDeckListItem,
  InterviewQuestionTablePage,
  InterviewStudySession,
  InterviewTopicOption,
} from "../src/types/api";
import { renderPage } from "./render";

const deck: InterviewDeckListItem = {
  id: "60000000-0000-4000-8000-000000000001",
  slug: "python-interview",
  title: "Python · вопросы с собеседований",
  description: "Карточки по Python Backend",
  track_id: "40000000-0000-4000-8000-000000000001",
  track_slug: "python",
  track_title: "Python",
  stats: {
    available_cards: 25,
    selected_categories: 1,
    total_categories: 3,
    total_cards: 10,
    learned_cards: 4,
    remaining_cards: 6,
    due_cards: 2,
    progress_percent: 40,
  },
};

const topics: InterviewTopicOption[] = [
  {
    name: "Конкурентность в Python",
    total_cards: 10,
    frequent_cards: 7,
    is_selected: true,
  },
  {
    name: "Архитектура ПО",
    total_cards: 15,
    frequent_cards: 5,
    is_selected: false,
  },
];

const session: InterviewStudySession = {
  deck,
  cards: [
    {
      id: "61000000-0000-4000-8000-000000000001",
      slug: "python-gil",
      category: "Конкурентность в Python",
      subcategory: null,
      companies: "Яндекс, VK",
      question_markdown: "## Что такое GIL?",
      answer_markdown:
        "**GIL** блокирует параллельное исполнение Python-байткода.",
      frequency: "frequent",
      is_new: true,
      repetitions: 0,
    },
  ],
};

const questionTable: InterviewQuestionTablePage = {
  deck,
  items: [
    {
      id: session.cards[0]!.id,
      slug: session.cards[0]!.slug,
      category: session.cards[0]!.category,
      subcategory: session.cards[0]!.subcategory,
      question_markdown: session.cards[0]!.question_markdown,
      answer_markdown: session.cards[0]!.answer_markdown,
      frequency: session.cards[0]!.frequency,
      learned: true,
      learned_at: "2026-08-20T00:00:00Z",
      repetitions: 2,
      due_at: "2026-09-20T00:00:00Z",
    },
    {
      id: "61000000-0000-4000-8000-000000000099",
      slug: "python-indexes",
      category: "Базы данных",
      subcategory: "PostgreSQL",
      question_markdown: "Какие индексы PostgreSQL вы знаете?",
      answer_markdown: "B-tree, Hash, GiST, SP-GiST, GIN и BRIN.",
      frequency: "occasional",
      learned: false,
      learned_at: null,
      repetitions: 0,
      due_at: null,
    },
  ],
  total: 2,
  limit: 25,
  offset: 0,
};

const adminTrack: AdminTrackRead = {
  id: deck.track_id,
  slug: "python",
  title: "Python",
  description: null,
  position: 0,
  is_published: true,
  roadmaps: [],
  student_ids: [],
};

const adminDeck: AdminInterviewDeckRead = {
  id: deck.id,
  track_id: deck.track_id,
  track_slug: "python",
  track_title: "Python",
  slug: deck.slug,
  title: deck.title,
  description: deck.description,
  position: 0,
  is_published: true,
  cards: [],
};

const automaticCard: AdminInterviewCardRead = {
  id: "61000000-0000-4000-8000-000000000002",
  slug: "python-asyncio",
  category: "Асинхронность",
  subcategory: null,
  companies: null,
  source_number: null,
  source_occurrence: null,
  question_markdown: "## Что такое event loop?",
  answer_markdown: "Цикл событий планирует выполнение корутин.",
  frequency: "occasional",
  frequency_override: null,
  frequency_mode: "automatic",
  frequency_threshold: 3,
  position: 0,
  is_published: true,
  asked_count: 2,
  updated_at: "2026-08-05T00:00:00Z",
};

const automaticAdminDeck: AdminInterviewDeckRead = {
  ...adminDeck,
  cards: [automaticCard],
};

afterEach(() => vi.restoreAllMocks());

const student = {
  id: "20000000-0000-4000-8000-000000000001",
  telegram_id: 987654321,
  first_name: "Иван",
  last_name: null,
  email: null,
  role: "student" as const,
  onboarding_completed_at: "2026-08-01T00:00:00Z",
  is_active: true,
};

const admin = {
  ...student,
  id: "90000000-0000-4000-8000-000000000001",
  first_name: "Администратор",
  role: "admin" as const,
};

const mentor = {
  ...student,
  id: "80000000-0000-4000-8000-000000000001",
  first_name: "Ментор",
  role: "mentor" as const,
};

it("показывает изученные и оставшиеся карточки", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "interviewDecks").mockResolvedValue([deck]);
  vi.spyOn(api, "interviewProcesses").mockResolvedValue([]);
  renderPage(<InterviewsPage />, "/interviews", "/interviews");

  expect(await screen.findByText(deck.title)).toBeInTheDocument();
  expect(screen.getByText("Изучено 4 из 10")).toBeInTheDocument();
  expect(screen.getByText("Осталось: 6")).toBeInTheDocument();
  expect(screen.getByText("К повторению: 2")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Таблица вопросов" }),
  ).toHaveAttribute("href", "/interviews/python-interview/questions");
  expect(
    screen.getByRole("link", { name: "Продолжить карточки" }),
  ).toHaveAttribute("href", "/interviews/python-interview");
});

it("показывает таблицу вопросов, фильтрует её и сохраняет отметку", async () => {
  vi.spyOn(api, "interviewTopics").mockResolvedValue([
    topics[0]!,
    { ...topics[1]!, is_selected: true },
  ]);
  const tableRequest = vi
    .spyOn(api, "interviewQuestionTable")
    .mockResolvedValue(questionTable);
  const learnedRequest = vi
    .spyOn(api, "setInterviewQuestionLearned")
    .mockReturnValue(new Promise(() => undefined));

  renderPage(
    <InterviewQuestionsPage />,
    "/interviews/python-interview/questions",
    "/interviews/:deckSlug/questions",
  );

  const learnedQuestion = await screen.findByText("Что такое GIL?");
  const learnedRow = learnedQuestion.closest("tr");
  expect(learnedRow).toHaveClass("interview-question-row--learned");
  expect(learnedRow).toHaveTextContent("Выучен");
  expect(screen.queryByText(/блокирует параллельное/)).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: /Что такое GIL/ }));
  expect(screen.getByText(/блокирует параллельное/)).toBeInTheDocument();

  await userEvent.click(
    screen.getByRole("checkbox", {
      name: /Отметить выученным: Какие индексы PostgreSQL/,
    }),
  );
  expect(learnedRequest).toHaveBeenCalledWith(
    "61000000-0000-4000-8000-000000000099",
    true,
  );

  await userEvent.click(
    screen.getByRole("switch", { name: /Только частые вопросы/ }),
  );
  await userEvent.click(screen.getByText("Не выучены"));
  await userEvent.type(screen.getByLabelText("Поиск вопроса"), "индексы");

  await waitFor(() =>
    expect(tableRequest).toHaveBeenLastCalledWith(
      "python-interview",
      expect.objectContaining({
        frequentOnly: true,
        learned: "unlearned",
        query: "индексы",
      }),
    ),
  );
});

it("показывает админу личный дневник без общего списка треков учеников", async () => {
  vi.spyOn(api, "me").mockResolvedValue(admin);
  vi.spyOn(api, "interviewDecks").mockResolvedValue([deck]);
  vi.spyOn(api, "interviewProcesses").mockResolvedValue([]);
  const adminProcesses = vi.spyOn(api, "adminInterviewProcesses");

  renderPage(<InterviewsPage />, "/interviews", "/interviews");

  expect(await screen.findByText(deck.title)).toBeInTheDocument();
  expect(
    screen.queryByRole("heading", { name: "Все треки собеседований" }),
  ).not.toBeInTheDocument();
  expect(adminProcesses).not.toHaveBeenCalled();
  expect(
    screen.getByRole("link", { name: "Каталог собеседований" }),
  ).toHaveAttribute("href", "/interviews/catalog");
});

it("показывает ментору его личный дневник и создание трека", async () => {
  vi.spyOn(api, "me").mockResolvedValue(mentor);
  vi.spyOn(api, "interviewDecks").mockResolvedValue([deck]);
  const processes = vi.spyOn(api, "interviewProcesses").mockResolvedValue([]);

  renderPage(<InterviewsPage />, "/interviews", "/interviews");

  expect(
    await screen.findByRole("heading", { name: "Треки по компаниям" }),
  ).toBeInTheDocument();
  expect(processes).toHaveBeenCalledWith("all");
  expect(
    screen.getByRole("link", { name: "+ Добавить компанию" }),
  ).toHaveAttribute("href", "/interviews/journal/new");
  expect(
    screen.getByRole("link", { name: "Каталог собеседований" }),
  ).toHaveAttribute("href", "/interviews/catalog");
});

it("скрывает ответ до переворота карточки", async () => {
  vi.spyOn(api, "interviewSession").mockResolvedValue(session);
  vi.spyOn(api, "interviewTopics").mockResolvedValue(topics);
  renderPage(
    <InterviewStudyPage />,
    "/interviews/python-interview",
    "/interviews/:deckSlug",
  );

  expect(
    await screen.findByRole("heading", { name: "Что такое GIL?" }),
  ).toBeInTheDocument();
  expect(screen.queryByText(/блокирует параллельное/)).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Показать ответ" }));
  expect(screen.getByText(/блокирует параллельное/)).toBeInTheDocument();
  expect(screen.getByText("Частый вопрос")).toBeInTheDocument();
  expect(screen.getAllByText("Конкурентность в Python")).toHaveLength(2);
  expect(screen.getByText(/Яндекс, VK/)).toBeInTheDocument();
});

it("сохраняет самооценку ученика", async () => {
  vi.spyOn(api, "interviewSession").mockResolvedValue(session);
  vi.spyOn(api, "interviewTopics").mockResolvedValue(topics);
  const review = vi
    .spyOn(api, "reviewInterviewCard")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <InterviewStudyPage />,
    "/interviews/python-interview",
    "/interviews/:deckSlug",
  );

  await screen.findByRole("heading", { name: "Что такое GIL?" });
  await userEvent.click(screen.getByRole("button", { name: "Показать ответ" }));
  await userEvent.click(screen.getByRole("button", { name: /Помню/ }));

  expect(review).toHaveBeenCalledWith(session.cards[0]!.id, "good");
});

it("откладывает отлично знакомую карточку на месяц", async () => {
  vi.spyOn(api, "interviewSession").mockResolvedValue(session);
  vi.spyOn(api, "interviewTopics").mockResolvedValue(topics);
  const review = vi
    .spyOn(api, "reviewInterviewCard")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <InterviewStudyPage />,
    "/interviews/python-interview",
    "/interviews/:deckSlug",
  );

  await screen.findByRole("heading", { name: "Что такое GIL?" });
  await userEvent.click(screen.getByRole("button", { name: "Показать ответ" }));
  await userEvent.click(screen.getByRole("button", { name: /Знаю отлично/ }));

  expect(review).toHaveBeenCalledWith(session.cards[0]!.id, "known");
});

it("фильтрует частые карточки и ищет по всей выбранной колоде", async () => {
  const sessionRequest = vi
    .spyOn(api, "interviewSession")
    .mockResolvedValue(session);
  vi.spyOn(api, "interviewTopics").mockResolvedValue(topics);
  const searchRequest = vi
    .spyOn(api, "searchInterviewCards")
    .mockResolvedValue(session.cards);
  renderPage(
    <InterviewStudyPage />,
    "/interviews/python-interview",
    "/interviews/:deckSlug",
  );

  await screen.findByRole("heading", { name: "Что такое GIL?" });
  await userEvent.click(
    screen.getByRole("switch", { name: /Только частые вопросы/ }),
  );
  await waitFor(() =>
    expect(sessionRequest).toHaveBeenLastCalledWith("python-interview", true),
  );

  await userEvent.type(screen.getByLabelText("Поиск по карточкам"), "GIL");
  await waitFor(() =>
    expect(searchRequest).toHaveBeenCalledWith("python-interview", "GIL", true),
  );
  expect(
    await screen.findByRole("heading", { name: "Результаты поиска" }),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Что такое GIL/ }));
  expect(screen.getByText(/блокирует параллельное/)).toBeInTheDocument();
});

it("не выдаёт карточки до выбора пройденной темы", async () => {
  vi.spyOn(api, "interviewSession").mockResolvedValue({
    deck: {
      ...deck,
      stats: {
        ...deck.stats,
        selected_categories: 0,
        total_cards: 0,
        learned_cards: 0,
        remaining_cards: 0,
        due_cards: 0,
        progress_percent: 0,
      },
    },
    cards: [],
  });
  vi.spyOn(api, "interviewTopics").mockResolvedValue(
    topics.map((topic) => ({ ...topic, is_selected: false })),
  );
  const update = vi
    .spyOn(api, "updateInterviewTopics")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <InterviewStudyPage />,
    "/interviews/python-interview",
    "/interviews/:deckSlug",
  );

  expect(await screen.findByText("Сначала выберите темы")).toBeInTheDocument();
  await userEvent.click(screen.getByText("Выберите темы"));
  await userEvent.click(
    // jsdom cannot measure element height, so Mantine's Collapse never
    // reports the panel as visible here even though it is open — query
    // with hidden: true to look past that testing-environment limitation.
    screen.getByRole("checkbox", {
      name: /Конкурентность в Python/,
      hidden: true,
    }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить выбор", hidden: true }),
  );

  expect(update).toHaveBeenCalledWith("python-interview", [
    "Конкурентность в Python",
  ]);
});

it("администратор добавляет частую карточку в отдельную колоду", async () => {
  vi.spyOn(api, "adminTracks").mockResolvedValue([adminTrack]);
  const update = vi
    .spyOn(api, "updateAdminInterviewDeck")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<AdminInterviewDeckForm deck={adminDeck} />);

  await userEvent.click(
    screen.getByRole("button", { name: "+ Добавить карточку" }),
  );
  await userEvent.type(screen.getByLabelText(/^Slug карточки/), "python-gil");
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить колоду" }),
  );

  expect(update).toHaveBeenCalledWith(
    adminDeck.id,
    expect.objectContaining({
      track_id: deck.track_id,
      cards: [
        expect.objectContaining({
          slug: "python-gil",
          category: "Общее",
          frequency: "frequent",
          frequency_mode: "manual",
        }),
      ],
    }),
  );
});

it("сохраняет автоматический режим частотности карточки", async () => {
  vi.spyOn(api, "adminTracks").mockResolvedValue([adminTrack]);
  const update = vi
    .spyOn(api, "updateAdminInterviewDeck")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<AdminInterviewDeckForm deck={automaticAdminDeck} />);

  expect(
    screen.getByText("Частой после 3 разных собеседований. Сейчас: 2."),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("radiogroup", {
      name: "Как определяется частотность карточки 1",
    }),
  ).toBeInTheDocument();
  expect(
    screen
      .getAllByLabelText("Частота на собеседованиях")
      .some(
        (element) => element instanceof HTMLInputElement && element.disabled,
      ),
  ).toBe(true);

  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить колоду" }),
  );

  expect(update).toHaveBeenCalledWith(
    automaticAdminDeck.id,
    expect.objectContaining({
      cards: [
        expect.objectContaining({
          frequency: "occasional",
          frequency_mode: "automatic",
        }),
      ],
    }),
  );
});

it("не переводит автоматическую карточку в ручной режим при отдельном редактировании", async () => {
  vi.spyOn(api, "adminInterviewCard").mockResolvedValue(automaticCard);
  const update = vi
    .spyOn(api, "updateAdminInterviewCard")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <AdminInterviewCardEditPage />,
    `/admin/interviews/${adminDeck.id}/cards/${automaticCard.id}/edit`,
    "/admin/interviews/:deckId/cards/:cardId/edit",
  );

  expect(
    await screen.findByText(
      "Карточка станет частой после 3 разных собеседований. Сейчас: 2.",
    ),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("radiogroup", {
      name: "Как определяется частотность",
    }),
  ).toBeInTheDocument();
  expect(
    screen
      .getAllByLabelText("Частота")
      .some(
        (element) => element instanceof HTMLInputElement && element.disabled,
      ),
  ).toBe(true);

  await userEvent.click(screen.getByRole("button", { name: "Сохранить" }));

  expect(update).toHaveBeenCalledWith(
    adminDeck.id,
    automaticCard.id,
    expect.objectContaining({
      frequency: "occasional",
      frequency_mode: "automatic",
    }),
  );
});
