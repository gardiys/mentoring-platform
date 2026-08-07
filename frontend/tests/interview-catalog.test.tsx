import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { InterviewCatalogCompanyPage } from "../src/pages/InterviewCatalogCompanyPage";
import { InterviewCatalogPage } from "../src/pages/InterviewCatalogPage";
import type {
  InterviewCatalogCompanyDetail,
  InterviewCatalogCompanyListItem,
} from "../src/types/api";
import { renderPage } from "./render";

const company: InterviewCatalogCompanyListItem = {
  id: "73000000-0000-4000-8000-000000000001",
  name: "Яндекс",
  track_count: 2,
  interview_count: 4,
  last_interview_at: "2026-08-12T12:00:00Z",
  unviewed_count: 1,
  has_favorite: false,
};
const pythonTrackId = "30000000-0000-4000-8000-000000000001";
const authorId = "20000000-0000-4000-8000-000000000001";

const detail: InterviewCatalogCompanyDetail = {
  id: company.id,
  name: company.name,
  tracks: [
    {
      id: "70000000-0000-4000-8000-000000000001",
      author: {
        id: "20000000-0000-4000-8000-000000000001",
        name: "Иван",
        telegram_username: "ivan_backend",
      },
      recruiter_telegram_usernames: ["yandex_hr", "python_recruiter"],
      track_id: pythonTrackId,
      track_slug: "python",
      track_title: "Python",
      status: "closed",
      close_reason: "Позиция была заморожена",
      created_at: "2026-08-01T10:00:00Z",
      updated_at: "2026-08-12T12:00:00Z",
      stages: [
        {
          id: "71000000-0000-4000-8000-000000000001",
          stage_type: "technical_interview",
          scheduled_at: "2026-08-10T12:00:00Z",
          description: "Алгоритмы, Python и проектирование API",
          is_viewed: false,
          first_viewed_at: null,
          last_viewed_at: null,
          is_favorite: false,
          media: {
            filename: "interview.mp4",
            content_type: "video/mp4",
            size: 0,
          },
          attachments: [
            {
              id: "74000000-0000-4000-8000-000000000001",
              filename: "diagram.png",
              content_type: "image/png",
              size: 512,
              created_at: "2026-08-10T14:00:00Z",
            },
          ],
          comments: [
            {
              id: "75000000-0000-4000-8000-000000000001",
              author: {
                id: "20000000-0000-4000-8000-000000000002",
                name: "Мария",
                telegram_username: "maria_go",
              },
              body: "Полезно повторить оценку сложности алгоритмов",
              is_own: false,
              is_mentor_feedback: false,
              is_ai_feedback: false,
              created_at: "2026-08-11T10:00:00Z",
              updated_at: "2026-08-11T10:00:00Z",
            },
          ],
        },
      ],
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

it("ищет компании в каталоге", async () => {
  const list = vi
    .spyOn(api, "interviewCatalogCompanies")
    .mockResolvedValue({ items: [company], total: 1, limit: 24, offset: 0 });
  vi.spyOn(api, "interviewCatalogDirections").mockResolvedValue([
    { id: pythonTrackId, slug: "python", title: "Python" },
  ]);
  vi.spyOn(api, "interviewCatalogAuthors").mockResolvedValue([
    { id: authorId, name: "Иван", telegram_username: "ivan_backend" },
  ]);
  renderPage(
    <InterviewCatalogPage />,
    "/interviews/catalog",
    "/interviews/catalog",
  );

  expect(await screen.findByText("Яндекс")).toBeInTheDocument();
  expect(screen.getByText("2 треков")).toBeInTheDocument();
  await userEvent.type(
    screen.getByRole("textbox", { name: "Найти компанию" }),
    "Yandex",
  );

  await userEvent.click(screen.getByRole("textbox", { name: "Направление" }));
  await userEvent.keyboard("{ArrowDown}{Enter}");

  await userEvent.click(screen.getByRole("textbox", { name: "Автор" }));
  await userEvent.keyboard("{ArrowDown}{Enter}");

  await userEvent.click(
    screen.getByRole("textbox", { name: "Этап собеседования" }),
  );
  await userEvent.keyboard("{ArrowDown}{ArrowDown}{ArrowDown}{Enter}");
  await userEvent.click(screen.getByRole("textbox", { name: "Запись" }));
  await userEvent.keyboard("{ArrowDown}{Enter}");
  await userEvent.click(
    screen.getByRole("switch", { name: "Только треки с оффером" }),
  );
  await userEvent.click(
    screen.getByRole("switch", { name: "Только с AI разбором" }),
  );

  await waitFor(() =>
    expect(list).toHaveBeenCalledWith(
      {
        query: "Yandex",
        authorId,
        trackId: pythonTrackId,
        stageType: "technical_interview",
        hasOffer: true,
        mediaKind: "any",
        hasAiReview: true,
        favoritesOnly: false,
      },
      { limit: 24, offset: 0 },
    ),
  );
  expect(
    await screen.findByRole("link", { name: "Смотреть собеседования" }),
  ).toHaveAttribute(
    "href",
    `/interviews/catalog/${company.id}?q=Yandex&track_id=${pythonTrackId}&author_id=${authorId}&stage_type=technical_interview&media_kind=any&has_offer=true&has_ai_review=true`,
  );
});

it("показывает треки, запись, файлы и отправляет комментарий", async () => {
  vi.spyOn(api, "interviewCatalogCompany").mockResolvedValue(detail);
  const loadMedia = vi
    .spyOn(api, "interviewCatalogStageMedia")
    .mockResolvedValue("https://s3.example.test/interview.mp4?inline=true");
  const createComment = vi
    .spyOn(api, "createInterviewCatalogComment")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <InterviewCatalogCompanyPage />,
    `/interviews/catalog/${company.id}`,
    "/interviews/catalog/:companyId",
  );

  expect(
    await screen.findByRole("button", { name: /Техническое интервью/ }),
  ).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: /Техническое интервью/ }),
  );

  expect(await screen.findByText("Иван · @ivan_backend")).toBeInTheDocument();
  expect(screen.queryByText(/Петров/)).not.toBeInTheDocument();
  expect(screen.getByText("Мария · @maria_go")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "@yandex_hr", hidden: true }),
  ).toHaveAttribute("href", "https://t.me/yandex_hr");
  expect(api.interviewCatalogCompany).toHaveBeenCalledWith(company.id, {
    query: "",
    authorId: null,
    trackId: null,
    stageType: null,
    hasOffer: false,
    mediaKind: null,
    hasAiReview: false,
    favoritesOnly: false,
  });
  expect(
    screen.getByText("Алгоритмы, Python и проектирование API"),
  ).toBeInTheDocument();
  expect(screen.getByText(/размер не указан/)).toBeInTheDocument();
  expect(screen.getByText(/diagram.png/)).toBeInTheDocument();
  expect(screen.getByText(/Полезно повторить/)).toBeInTheDocument();

  await userEvent.click(
    screen.getByRole("button", { name: "Посмотреть", hidden: true }),
  );
  await waitFor(() => {
    const player = document.querySelector("video[controls]");
    expect(player).not.toBeNull();
    expect(player).toHaveAttribute(
      "src",
      "https://s3.example.test/interview.mp4?inline=true",
    );
    expect(player).toHaveAttribute(
      "controlslist",
      "nodownload noremoteplayback",
    );
    expect(player).toHaveAttribute("preload", "metadata");
    expect(player).toHaveAttribute("disablepictureinpicture");
  });
  expect(
    screen.getByText("Персональный просмотр · Копирование запрещено"),
  ).toBeInTheDocument();
  expect(api.interviewCatalogStageMedia).toHaveBeenCalledWith(
    detail.tracks[0]!.stages[0]!.id,
  );
  const firstPlayer = document.querySelector("video[controls]");
  expect(firstPlayer).not.toBeNull();
  fireEvent.error(firstPlayer!);
  await waitFor(() => expect(loadMedia).toHaveBeenCalledTimes(2));
  expect(document.querySelector("video[controls]")).not.toBe(firstPlayer);

  await userEvent.type(
    screen.getByRole("textbox", { name: "Ваш комментарий", hidden: true }),
    "Спасибо, очень полезный разбор",
  );
  await userEvent.click(
    screen.getByRole("button", {
      name: "Отправить комментарий",
      hidden: true,
    }),
  );
  expect(createComment).toHaveBeenCalledWith(detail.tracks[0]!.stages[0]!.id, {
    body: "Спасибо, очень полезный разбор",
  });
});

it("отмечает конкретный этап избранным", async () => {
  vi.spyOn(api, "interviewCatalogCompany").mockResolvedValue(detail);
  const favorite = vi
    .spyOn(api, "favoriteInterviewCatalogStage")
    .mockResolvedValue(undefined);
  renderPage(
    <InterviewCatalogCompanyPage />,
    `/interviews/catalog/${company.id}`,
    "/interviews/catalog/:companyId",
  );

  expect(await screen.findByText("Новое")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: /Техническое интервью/ }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "☆ В избранное", hidden: true }),
  );

  expect(favorite).toHaveBeenCalledWith(detail.tracks[0]!.stages[0]!.id);
});

it("избранное не распространяется на другие этапы того же трека", async () => {
  vi.spyOn(api, "interviewCatalogCompany").mockResolvedValue({
    ...detail,
    tracks: [
      {
        ...detail.tracks[0]!,
        stages: [
          { ...detail.tracks[0]!.stages[0]!, is_favorite: true },
          {
            ...detail.tracks[0]!.stages[0]!,
            id: "71000000-0000-4000-8000-000000000002",
            stage_type: "final_interview",
            description: "Финальный этап",
            is_favorite: false,
          },
        ],
      },
    ],
  });
  renderPage(
    <InterviewCatalogCompanyPage />,
    `/interviews/catalog/${company.id}`,
    "/interviews/catalog/:companyId",
  );

  await userEvent.click(
    await screen.findByRole("button", { name: /Техническое интервью/ }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: /Финальное интервью/ }),
  );

  expect(
    screen.getByRole("button", { name: "★ В избранном", hidden: true }),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: "☆ В избранное", hidden: true }),
  ).toBeInTheDocument();
});

it("показывает дату последнего просмотра у уже просмотренного этапа", async () => {
  vi.spyOn(api, "interviewCatalogCompany").mockResolvedValue({
    ...detail,
    tracks: [
      {
        ...detail.tracks[0]!,
        stages: [
          {
            ...detail.tracks[0]!.stages[0]!,
            is_viewed: true,
            first_viewed_at: "2026-08-05T09:00:00Z",
            last_viewed_at: "2026-08-13T09:00:00Z",
          },
        ],
      },
    ],
  });
  renderPage(
    <InterviewCatalogCompanyPage />,
    `/interviews/catalog/${company.id}`,
    "/interviews/catalog/:companyId",
  );

  expect(
    await screen.findByText(/Просмотрено 13 августа 2026/),
  ).toBeInTheDocument();
  expect(screen.queryByText("Новое")).not.toBeInTheDocument();
});

it("отмечает этап просмотренным по нажатию кнопки", async () => {
  vi.spyOn(api, "interviewCatalogCompany").mockResolvedValue(detail);
  const markViewed = vi
    .spyOn(api, "markInterviewCatalogStageViewed")
    .mockResolvedValue(undefined);
  renderPage(
    <InterviewCatalogCompanyPage />,
    `/interviews/catalog/${company.id}`,
    "/interviews/catalog/:companyId",
  );

  expect(await screen.findByText("Новое")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: /Техническое интервью/ }),
  );
  await userEvent.click(
    screen.getByRole("button", {
      name: "Отметить просмотренным",
      hidden: true,
    }),
  );

  expect(markViewed).toHaveBeenCalledWith(detail.tracks[0]!.stages[0]!.id);
});

it("отмечает этап просмотренным при открытии записи", async () => {
  const companySpy = vi.spyOn(api, "interviewCatalogCompany");
  companySpy.mockResolvedValueOnce(detail).mockResolvedValueOnce({
    ...detail,
    tracks: [
      {
        ...detail.tracks[0]!,
        stages: [
          {
            ...detail.tracks[0]!.stages[0]!,
            is_viewed: true,
            first_viewed_at: "2026-08-13T09:00:00Z",
            last_viewed_at: "2026-08-13T09:00:00Z",
          },
        ],
      },
    ],
  });
  vi.spyOn(api, "interviewCatalogStageMedia").mockResolvedValue(
    "https://s3.example.test/interview.mp4?inline=true",
  );
  renderPage(
    <InterviewCatalogCompanyPage />,
    "/interviews/catalog/73000000-0000-4000-8000-000000000001",
    "/interviews/catalog/:companyId",
  );

  expect(await screen.findByText("Новое")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: /Техническое интервью/ }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Посмотреть", hidden: true }),
  );

  expect(
    await screen.findByText(/Просмотрено 13 августа 2026/),
  ).toBeInTheDocument();
});

it("раскрывает нужный раздел и подсвечивает этап при переходе по ссылке из истории", async () => {
  vi.spyOn(api, "interviewCatalogCompany").mockResolvedValue(detail);
  const targetStageId = detail.tracks[0]!.stages[0]!.id;
  renderPage(
    <InterviewCatalogCompanyPage />,
    `/interviews/catalog/${company.id}?stage=${targetStageId}`,
    "/interviews/catalog/:companyId",
  );

  const control = await screen.findByRole("button", {
    name: /Техническое интервью/,
  });
  expect(control).toHaveAttribute("aria-expanded", "true");
  expect(
    screen.getByRole("button", { name: "Посмотреть", hidden: true }),
  ).toBeInTheDocument();
  expect(document.getElementById(`stage-${targetStageId}`)).toHaveStyle({
    borderColor: "var(--mantine-color-blue-6)",
  });
});
