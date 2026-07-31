import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminInterviewDeckForm } from "../src/features/admin/AdminInterviewDeckForm";
import { InterviewStudyPage } from "../src/pages/InterviewStudyPage";
import { InterviewsPage } from "../src/pages/InterviewsPage";
import type {
  AdminInterviewDeckRead,
  AdminTrackRead,
  InterviewDeckListItem,
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

afterEach(() => vi.restoreAllMocks());

it("показывает изученные и оставшиеся карточки", async () => {
  vi.spyOn(api, "interviewDecks").mockResolvedValue([deck]);
  renderPage(<InterviewsPage />, "/interviews", "/interviews");

  expect(await screen.findByText(deck.title)).toBeInTheDocument();
  expect(screen.getByText("Изучено 4 из 10")).toBeInTheDocument();
  expect(screen.getByText("Осталось: 6")).toBeInTheDocument();
  expect(screen.getByText("К повторению: 2")).toBeInTheDocument();
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
  await userEvent.click(
    screen.getByRole("checkbox", { name: /Конкурентность в Python/ }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить выбор" }),
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
        }),
      ],
    }),
  );
});
