import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { InterviewProcessCreatePage } from "../src/pages/InterviewProcessCreatePage";
import { InterviewProcessPage } from "../src/pages/InterviewProcessPage";
import { InterviewsPage } from "../src/pages/InterviewsPage";
import type {
  InterviewProcessDetail,
  InterviewProcessSummary,
} from "../src/types/api";
import { renderPage } from "./render";

const processSummary: InterviewProcessSummary = {
  id: "70000000-0000-4000-8000-000000000001",
  company_name: "Яндекс",
  recruiter_telegram_usernames: ["first_recruiter"],
  track_id: "30000000-0000-4000-8000-000000000001",
  track_slug: "python",
  track_title: "Python",
  status: "active",
  close_reason: null,
  closed_at: null,
  stage_count: 1,
  next_stage_at: "2026-08-05T12:00:00Z",
  has_offer_file: false,
  created_at: "2026-08-01T10:00:00Z",
  updated_at: "2026-08-01T10:00:00Z",
};

const pythonDirection = {
  id: processSummary.track_id,
  slug: "python",
  title: "Python",
};

beforeEach(() => {
  vi.spyOn(api, "interviewDirections").mockResolvedValue([
    pythonDirection,
    {
      id: "30000000-0000-4000-8000-000000000002",
      slug: "go",
      title: "Go",
    },
  ]);
});

async function selectPythonDirection() {
  const input = screen.getByRole("textbox", { name: "Направление" });
  await waitFor(() => expect(input).toBeEnabled());
  await userEvent.click(input);
  await userEvent.keyboard("{ArrowDown}{Enter}");
}

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

const processDetail: InterviewProcessDetail = {
  ...processSummary,
  stages: [
    {
      id: "71000000-0000-4000-8000-000000000001",
      stage_type: "technical_screening",
      scheduled_at: "2026-08-05T12:00:00Z",
      description: "Алгоритмы и Python",
      media: null,
      attachments: [],
      created_at: "2026-08-01T10:00:00Z",
      updated_at: "2026-08-01T10:00:00Z",
    },
  ],
  offer: null,
};

afterEach(() => vi.restoreAllMocks());

it("показывает активные и завершённые треки компаний", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "interviewDecks").mockResolvedValue([]);
  vi.spyOn(api, "interviewProcesses").mockResolvedValue([
    processSummary,
    {
      ...processSummary,
      id: "70000000-0000-4000-8000-000000000002",
      company_name: "Ozon",
      status: "offer",
      stage_count: 4,
      next_stage_at: null,
    },
  ]);

  renderPage(<InterviewsPage />);

  expect(await screen.findByText("Яндекс")).toBeInTheDocument();
  expect(screen.getByText("Активный процесс")).toBeInTheDocument();
  expect(screen.getByText("Ozon")).toBeInTheDocument();
  expect(screen.getByText("Получен оффер")).toBeInTheDocument();
});

it("создаёт новый трек компании", async () => {
  vi.spyOn(api, "interviewCompanySuggestions").mockResolvedValue([]);
  const create = vi
    .spyOn(api, "createInterviewProcess")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<InterviewProcessCreatePage />);
  await selectPythonDirection();

  await userEvent.type(
    screen.getByRole("textbox", { name: "Компания" }),
    "Avito",
  );
  await userEvent.type(
    screen.getByRole("textbox", { name: "Telegram рекрутеров" }),
    "@avito_hr{Enter}",
  );
  await userEvent.click(screen.getByRole("button", { name: "Создать трек" }));

  await waitFor(() =>
    expect(create).toHaveBeenCalledWith({
      company_name: "Avito",
      track_id: pythonDirection.id,
      company_id: null,
      company_alias: null,
      recruiter_telegram_usernames: ["@avito_hr"],
    }),
  );
});

it("предлагает связать свободный ввод с найденной компанией", async () => {
  vi.spyOn(api, "interviewCompanySuggestions").mockResolvedValue([
    {
      id: "72000000-0000-4000-8000-000000000001",
      name: "Wildberries",
    },
  ]);
  const create = vi
    .spyOn(api, "createInterviewProcess")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<InterviewProcessCreatePage />);
  await selectPythonDirection();

  await userEvent.type(screen.getByRole("textbox", { name: "Компания" }), "WB");
  await userEvent.click(screen.getByRole("button", { name: "Создать трек" }));
  expect(
    await screen.findByText("Возможно, компания уже есть"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Вы ввели «WB». Есть ли ваша компания среди найденных?"),
  ).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Связать с «Wildberries»" }),
  );

  expect(create).toHaveBeenCalledWith({
    company_name: "Wildberries",
    track_id: pythonDirection.id,
    company_id: "72000000-0000-4000-8000-000000000001",
    company_alias: "WB",
    recruiter_telegram_usernames: [],
  });
});

it("создаёт новую компанию после отказа от найденных совпадений", async () => {
  vi.spyOn(api, "interviewCompanySuggestions").mockResolvedValue([
    {
      id: "72000000-0000-4000-8000-000000000001",
      name: "Wildberries",
    },
  ]);
  const create = vi
    .spyOn(api, "createInterviewProcess")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<InterviewProcessCreatePage />);
  await selectPythonDirection();

  await userEvent.type(
    screen.getByRole("textbox", { name: "Компания" }),
    "Wildberries Lab",
  );
  await userEvent.click(screen.getByRole("button", { name: "Создать трек" }));
  await userEvent.click(
    await screen.findByRole("button", {
      name: "Моей компании нет — создать новую",
    }),
  );

  expect(create).toHaveBeenCalledWith({
    company_name: "Wildberries Lab",
    track_id: pythonDirection.id,
    company_id: null,
    company_alias: null,
    recruiter_telegram_usernames: [],
  });
});

it("запоминает введённое название как алиас выбранной компании", async () => {
  vi.spyOn(api, "interviewCompanySuggestions").mockResolvedValue([
    {
      id: "72000000-0000-4000-8000-000000000001",
      name: "Wildberries",
    },
  ]);
  const create = vi
    .spyOn(api, "createInterviewProcess")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<InterviewProcessCreatePage />);
  await selectPythonDirection();

  await userEvent.type(screen.getByRole("textbox", { name: "Компания" }), "WB");
  expect(await screen.findByText("Wildberries")).toBeInTheDocument();
  await userEvent.click(screen.getByText("Wildberries"));
  expect(
    await screen.findByText(
      "То, что вы ввели, — альтернативное название компании?",
    ),
  ).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", {
      name: "Да, это альтернативное название",
    }),
  );
  await userEvent.click(screen.getByRole("button", { name: "Создать трек" }));

  expect(create).toHaveBeenCalledWith({
    company_name: "Wildberries",
    track_id: pythonDirection.id,
    company_id: "72000000-0000-4000-8000-000000000001",
    company_alias: "WB",
    recruiter_telegram_usernames: [],
  });
});

it("не связывает незавершённый ввод с выбранной компанией без подтверждения", async () => {
  vi.spyOn(api, "interviewCompanySuggestions").mockResolvedValue([
    {
      id: "72000000-0000-4000-8000-000000000001",
      name: "Wildberries",
    },
  ]);
  const create = vi
    .spyOn(api, "createInterviewProcess")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(<InterviewProcessCreatePage />);
  await selectPythonDirection();

  await userEvent.type(
    screen.getByRole("textbox", { name: "Компания" }),
    "Wild",
  );
  await userEvent.click(await screen.findByText("Wildberries"));
  await userEvent.click(await screen.findByRole("button", { name: "Нет" }));
  await userEvent.click(screen.getByRole("button", { name: "Создать трек" }));

  expect(create).toHaveBeenCalledWith({
    company_name: "Wildberries",
    track_id: pythonDirection.id,
    company_id: "72000000-0000-4000-8000-000000000001",
    company_alias: null,
    recruiter_telegram_usernames: [],
  });
});

it("редактирует Telegram никнеймы рекрутеров в треке", async () => {
  vi.spyOn(api, "interviewProcess").mockResolvedValue(processDetail);
  const saveRecruiters = vi
    .spyOn(api, "setInterviewProcessRecruiters")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <InterviewProcessPage />,
    `/interviews/journal/${processDetail.id}`,
    "/interviews/journal/:processId",
  );

  const input = await screen.findByRole("textbox", {
    name: "Telegram никнеймы",
  });
  await userEvent.type(input, "@second_recruiter{Enter}");
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить рекрутеров" }),
  );

  expect(saveRecruiters).toHaveBeenCalledWith(processDetail.id, {
    recruiter_telegram_usernames: ["@first_recruiter", "@second_recruiter"],
  });
});

it("добавляет этап и позволяет закрыть процесс с причиной", async () => {
  vi.spyOn(api, "interviewProcess").mockResolvedValue(processDetail);
  const createStage = vi
    .spyOn(api, "createInterviewProcessStage")
    .mockReturnValue(new Promise(() => undefined));
  const setOutcome = vi
    .spyOn(api, "setInterviewProcessOutcome")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <InterviewProcessPage />,
    `/interviews/journal/${processDetail.id}`,
    "/interviews/journal/:processId",
  );

  expect(
    await screen.findByRole("heading", {
      name: "Технический скрининг",
      level: 3,
    }),
  ).toBeInTheDocument();
  expect(screen.getByText("Алгоритмы и Python")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Добавить собеседование" }),
  );
  expect(createStage).toHaveBeenCalledWith(
    processDetail.id,
    expect.objectContaining({ stage_type: "screening", description: null }),
  );

  await userEvent.type(
    screen.getByLabelText(/^Причина отказа/),
    "Позиция заморожена",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Закрыть процесс" }),
  );
  expect(setOutcome).toHaveBeenCalledWith(processDetail.id, {
    status: "closed",
    close_reason: "Позиция заморожена",
  });
});

it("восстанавливает закрытый трек и сохраняет причину прошлого отказа", async () => {
  const closedProcess: InterviewProcessDetail = {
    ...processDetail,
    status: "closed",
    close_reason: "Позиция заморожена",
    closed_at: "2026-08-10T12:00:00Z",
  };
  vi.spyOn(api, "interviewProcess").mockResolvedValue(closedProcess);
  const setOutcome = vi
    .spyOn(api, "setInterviewProcessOutcome")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <InterviewProcessPage />,
    `/interviews/journal/${closedProcess.id}`,
    "/interviews/journal/:processId",
  );

  expect(await screen.findByText("Причина закрытия")).toBeInTheDocument();
  expect(screen.getByText("Позиция заморожена")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Восстановить трек" }),
  );

  expect(setOutcome).toHaveBeenCalledWith(closedProcess.id, {
    status: "active",
    close_reason: null,
  });
});

it("прикрепляет аудиозапись к этапу", async () => {
  vi.spyOn(api, "interviewProcess").mockResolvedValue(processDetail);
  const upload = vi
    .spyOn(api, "uploadInterviewStageMedia")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <InterviewProcessPage />,
    `/interviews/journal/${processDetail.id}`,
    "/interviews/journal/:processId",
  );
  await screen.findByRole("heading", {
    name: "Технический скрининг",
    level: 3,
  });

  const file = new File(["audio"], "interview.mp3", { type: "audio/mpeg" });
  const mediaInput = document.querySelector<HTMLInputElement>(
    'input[type="file"][accept="audio/*,video/*"]',
  );
  expect(mediaInput).not.toBeNull();
  await userEvent.upload(mediaInput!, file);
  await userEvent.click(screen.getByRole("button", { name: "Загрузить" }));

  expect(upload).toHaveBeenCalledWith(
    processDetail.id,
    processDetail.stages[0]!.id,
    file,
  );
});

it("проигрывает видеозапись собеседования на странице", async () => {
  const processWithVideo: InterviewProcessDetail = {
    ...processDetail,
    stages: [
      {
        ...processDetail.stages[0]!,
        media: {
          filename: "interview.mp4",
          content_type: "video/mp4",
          size: 1024,
        },
      },
    ],
  };
  vi.spyOn(api, "interviewProcess").mockResolvedValue(processWithVideo);
  vi.spyOn(api, "viewInterviewStageMedia").mockResolvedValue(
    "https://s3.example.test/interview.mp4?inline=true",
  );
  renderPage(
    <InterviewProcessPage />,
    `/interviews/journal/${processWithVideo.id}`,
    "/interviews/journal/:processId",
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "Посмотреть запись" }),
  );
  await waitFor(() => {
    const player = document.querySelector<HTMLVideoElement>("video[controls]");
    expect(player).not.toBeNull();
    expect(player?.src).toContain("interview.mp4?inline=true");
  });
});

it("добавляет несколько файлов к описанию собеседования", async () => {
  vi.spyOn(api, "interviewProcess").mockResolvedValue(processDetail);
  const upload = vi
    .spyOn(api, "uploadInterviewStageAttachment")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <InterviewProcessPage />,
    `/interviews/journal/${processDetail.id}`,
    "/interviews/journal/:processId",
  );
  await screen.findByText("Дополнительные материалы");

  const attachmentInput = document.querySelector<HTMLInputElement>(
    'input[type="file"][multiple]',
  );
  expect(attachmentInput).not.toBeNull();
  const diagram = new File(["image"], "diagram.png", { type: "image/png" });
  const notes = new File(["notes"], "notes.txt", { type: "text/plain" });
  await userEvent.upload(attachmentInput!, [diagram, notes]);
  await userEvent.click(
    screen.getByRole("button", { name: "Загрузить файлы" }),
  );

  expect(upload).toHaveBeenCalledWith(
    processDetail.id,
    processDetail.stages[0]!.id,
    diagram,
  );
});

it("фиксирует оффер с PDF-файлом", async () => {
  vi.spyOn(api, "interviewProcess").mockResolvedValue(processDetail);
  vi.spyOn(api, "setInterviewProcessOutcome").mockResolvedValue({
    ...processDetail,
    status: "offer",
  });
  const upload = vi
    .spyOn(api, "uploadInterviewOffer")
    .mockReturnValue(new Promise(() => undefined));
  renderPage(
    <InterviewProcessPage />,
    `/interviews/journal/${processDetail.id}`,
    "/interviews/journal/:processId",
  );
  await screen.findByText("Получен оффер");

  const offer = new File(["pdf"], "offer.pdf", { type: "application/pdf" });
  const offerInput = document.querySelector<HTMLInputElement>(
    'input[type="file"][accept="application/pdf,image/*"]',
  );
  expect(offerInput).not.toBeNull();
  await userEvent.upload(offerInput!, offer);
  await userEvent.click(screen.getByRole("button", { name: "Отметить оффер" }));

  await waitFor(() =>
    expect(upload).toHaveBeenCalledWith(processDetail.id, offer),
  );
});

it("отменяет ошибочно отмеченный оффер и возвращает трек в работу", async () => {
  const processWithOffer: InterviewProcessDetail = {
    ...processDetail,
    status: "offer",
    has_offer_file: true,
    offer: {
      filename: "offer.pdf",
      content_type: "application/pdf",
      size: 1024,
    },
  };
  vi.spyOn(api, "interviewProcess").mockResolvedValue(processWithOffer);
  const cancel = vi.spyOn(api, "deleteInterviewOffer").mockResolvedValue();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  renderPage(
    <InterviewProcessPage />,
    `/interviews/journal/${processWithOffer.id}`,
    "/interviews/journal/:processId",
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "Отменить оффер" }),
  );

  expect(window.confirm).toHaveBeenCalled();
  expect(cancel).toHaveBeenCalledWith(processWithOffer.id);
});
