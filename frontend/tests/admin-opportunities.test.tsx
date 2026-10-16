import {
  act,
  fireEvent,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AppLayout } from "../src/components/AppLayout";
import {
  workspaceApi,
  type ConsultationDetail,
  type GoDetail,
  type WorkspacePage,
} from "../src/features/opportunities/workspaceApi";
import { copilotApi } from "../src/features/copilot/api";
import { AdminOpportunitiesPage } from "../src/pages/AdminOpportunitiesPage";
import { renderPage } from "./render";
import { adminGoQuestionnaire } from "./legalFixtures";

afterEach(() => {
  delete window.Telegram;
  delete (window as Window & { TelegramWebviewProxy?: unknown })
    .TelegramWebviewProxy;
  vi.restoreAllMocks();
});
const student = {
  id: "student-1",
  first_name: "Иван",
  last_name: "Петров",
  telegram_username: "ivan",
  email: "student@example.com",
};
const mentor = {
  id: "mentor-1",
  first_name: "Антон",
  last_name: "Ментор",
  telegram_username: "mentor",
};
const consultation: ConsultationDetail = {
  id: "consultation-1",
  student,
  mentor,
  consultation_type: "technical_mock",
  brief: "Подготовиться к техническому собеседованию",
  price_kopecks: 400_000,
  mentor_reward_kopecks: 250_000,
  duration_minutes: 60,
  status: "paid",
  scheduled_at: null,
  paid_at: "2026-10-15T10:00:00Z",
  completed_at: null,
  admin_note: null,
  written_summary: null,
  created_at: "2026-10-14T10:00:00Z",
  updated_at: "2026-10-15T10:00:00Z",
  stage: "needs_schedule",
  next_action: "Согласовать время встречи",
  waiting_since: "2026-10-15T10:00:00Z",
  overdue: false,
  internal_note: null,
  last_payment: null,
  history: [],
  available_mentors: [mentor],
  requested_mentor_known: false,
};
const go: GoDetail = {
  id: "go-1",
  student,
  motivation: "Хочу перейти с Python на Go",
  status: "submitted",
  upfront_price_kopecks: 3_000_000,
  success_fee_percent: 100,
  approved_at: null,
  terms_accepted_at: null,
  paid_at: null,
  admin_note: null,
  terms_version: 1,
  terms_snapshot: {},
  terms_expires_at: null,
  accepted_terms_snapshot: null,
  created_at: "2026-10-14T10:00:00Z",
  updated_at: "2026-10-14T10:00:00Z",
  stage: "new",
  next_action: "Рассмотреть заявку",
  waiting_since: "2026-10-14T10:00:00Z",
  overdue: false,
  internal_note: null,
  last_payment: null,
  payment_block_reason: null,
  history: [],
};

function openPage(
  item = consultation,
  path = `/admin/opportunities?consultation=${item.id}`,
  empty = false,
  goItem: GoDetail = go,
) {
  const page: WorkspacePage = {
    items: [
      {
        product: "consultations",
        id: item.id,
        student,
        title: "Техническое мок-собеседование",
        status: item.status,
        stage: item.stage,
        next_action: item.next_action,
        waiting_since: item.waiting_since,
        overdue: item.overdue,
        key_date: item.created_at,
        amount_kopecks: item.price_kopecks,
        mentor,
      },
    ],
    total: 1,
    counts: { [item.stage]: 1 },
    page: 1,
    page_size: 25,
  };
  vi.spyOn(workspaceApi, "summary").mockResolvedValue({
    needs_action_total: 1,
    overdue_total: 0,
    consultations: { [item.stage]: 1 },
    go_transition: {},
    python_repeat: {},
  });
  vi.spyOn(workspaceApi, "page").mockResolvedValue(
    empty ? { ...page, items: [], counts: {}, total: 0 } : page,
  );
  vi.spyOn(workspaceApi, "settings").mockResolvedValue({
    consultation_types: [],
    consultation_mentors: [{ ...mentor, is_enabled: true }],
    go_transition_description_markdown: "Описание программы Go",
  });
  vi.spyOn(workspaceApi, "consultation").mockResolvedValue(item);
  vi.spyOn(workspaceApi, "go").mockResolvedValue(goItem);
  return renderPage(<AdminOpportunitiesPage />, path, "/admin/opportunities/*");
}

it("показывает администратору счётчик возможностей в меню", async () => {
  vi.spyOn(api, "me").mockResolvedValue({
    id: "admin-1",
    first_name: "Админ",
    last_name: null,
    telegram_id: 1,
    email: null,
    role: "admin",
    is_active: true,
    onboarding_completed_at: "2026-10-01T00:00:00Z",
  });
  vi.spyOn(api, "notifications").mockResolvedValue({
    items: [],
    unread_count: 0,
    total: 0,
    limit: 20,
    offset: 0,
  });
  vi.spyOn(copilotApi, "access").mockResolvedValue({
    allowed: true,
    student_allowed: true,
    students_enabled: true,
    learning_status: "active",
    reason: "",
  });
  vi.spyOn(workspaceApi, "summary").mockResolvedValue({
    needs_action_total: 7,
    overdue_total: 2,
    consultations: {},
    go_transition: {},
    python_repeat: {},
  });
  renderPage(<AppLayout />, "/admin/opportunities", "/admin/opportunities");
  expect(
    await screen.findByLabelText("Возможности требуют действия"),
  ).toHaveTextContent("7");
});

it.each(["paid", "scheduled"] as const)(
  "сохраняет посимвольный ввод и завершает консультацию %s",
  async (status) => {
    const user = userEvent.setup();
    const item = {
      ...consultation,
      status,
      stage: status === "paid" ? "needs_schedule" : "scheduled",
    };
    const complete = vi
      .spyOn(workspaceApi, "completeConsultation")
      .mockResolvedValue({ ...item, status: "completed", stage: "completed" });
    openPage(item);
    await user.click(
      await screen.findByRole("button", {
        name: status === "paid" ? "Отметить проведённой" : "Завершить",
      }),
    );
    const summaryInput = screen.getByLabelText("Итог для выпускника");
    const noteInput = screen.getByLabelText("Внутренняя заметка");
    const button = screen.getByRole("button", {
      name: "Завершить консультацию",
    });
    expect(button).toBeDisabled();
    expect(
      screen.getByText("Ещё 10 символов, чтобы завершить"),
    ).toBeInTheDocument();
    expect(summaryInput).toHaveAttribute("maxlength", "10000");
    expect(noteInput).toHaveAttribute("maxlength", "5000");
    const summary = "И".repeat(40),
      note = "К".repeat(20);
    await user.type(summaryInput, summary);
    await user.type(noteInput, note);
    expect(summaryInput).toHaveValue(summary);
    expect(noteInput).toHaveValue(note);
    expect(screen.getByText("40 / 10 000")).toBeInTheDocument();
    vi.mocked(workspaceApi.consultation).mockResolvedValue({
      ...item,
      status: "completed",
      stage: "completed",
      written_summary: summary,
    });
    await user.click(button);
    await waitFor(() =>
      expect(complete).toHaveBeenCalledWith(item.id, {
        written_summary: summary,
        held_at: expect.any(String),
      }),
    );
    expect(
      await screen.findByRole("button", { name: "Исправить итог" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Внутренняя заметка")).toHaveValue(note);
  },
);

it.each(["payment", "checkout"] as const)(
  "показывает заполненную анкету Go из %s",
  async (source) => {
    openPage(consultation, "/admin/opportunities?go=go-1", false, {
      ...go,
      questionnaire: { ...adminGoQuestionnaire, source, application_id: go.id },
    });
    expect(
      await screen.findByText("Анкета перехода Python → Go"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        source === "payment"
          ? /Сведения зафиксированы при оплате/
          : /Сведения заполнены перед оплатой/,
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Python backend developer")).toBeInTheDocument();
    expect(screen.getByText("Python, PostgreSQL, Go")).toBeInTheDocument();
    expect(
      screen.getByText("Оффер на Go-позицию на рассмотрении"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("Нет")).toHaveLength(2);
    expect(screen.queryByText("existing_offers")).not.toBeInTheDocument();
  },
);

it("сохраняет набранный комментарий к решению по Go", async () => {
  const user = userEvent.setup();
  const approve = vi
    .spyOn(workspaceApi, "approveGo")
    .mockResolvedValue({ ...go, status: "approved" });
  openPage(consultation, "/admin/opportunities?go=go-1");
  const input = await screen.findByLabelText("Сообщение выпускнику");
  const note = "Р".repeat(20);
  await user.type(input, note);
  expect(input).toHaveValue(note);
  await user.click(screen.getByRole("button", { name: "Одобрить" }));
  await waitFor(() =>
    expect(approve).toHaveBeenCalledWith("go-1", { message_to_student: note }),
  );
});

it.each([null, "Сохранённый ранее черновик"])(
  "назначает время отдельной командой без черновика (%s)",
  async (saved) => {
    const user = userEvent.setup();
    const item = { ...consultation, written_summary: saved };
    const schedule = vi
      .spyOn(workspaceApi, "scheduleConsultation")
      .mockResolvedValue(item);
    openPage(item);
    await user.click(
      await screen.findByRole("button", { name: "Отметить проведённой" }),
    );
    const input = screen.getByLabelText("Итог для выпускника");
    await user.clear(input);
    await user.type(input, "Незаконченный текст итога");
    await user.click(
      screen.getByRole("button", { name: "К назначению времени" }),
    );
    fireEvent.change(screen.getByLabelText("Дата и время встречи"), {
      target: { value: "2026-10-20T15:30" },
    });
    await user.click(screen.getByRole("button", { name: "Назначить время" }));
    await waitFor(() =>
      expect(schedule).toHaveBeenCalledWith(item.id, {
        scheduled_at: new Date(2026, 9, 20, 15, 30).toISOString(),
      }),
    );
  },
);

it("открывает карточку ссылкой и закрывает кнопкой Назад", async () => {
  const user = userEvent.setup();
  const result = openPage(consultation, "/admin/opportunities");
  await user.click(
    await screen.findByRole("button", { name: "Открыть заявку Иван" }),
  );
  expect(result.router.state.location.search).toContain(
    "consultation=consultation-1",
  );
  expect(
    await screen.findByLabelText("Внутренняя заметка"),
  ).toBeInTheDocument();
  await act(async () => {
    await result.router.navigate(-1);
  });
  await waitFor(() =>
    expect(
      screen.queryByLabelText("Внутренняя заметка"),
    ).not.toBeInTheDocument(),
  );
});

it("требует причину отклонения и не отправляет короткую причину", async () => {
  const user = userEvent.setup();
  const reject = vi.spyOn(workspaceApi, "rejectGo").mockResolvedValue(go);
  openPage(consultation, "/admin/opportunities?go=go-1");
  await user.click(await screen.findByRole("button", { name: "Отклонить" }));
  const button = screen.getByRole("button", { name: "Подтвердить решение" });
  expect(button).toBeDisabled();
  const reason = "Недостаточно времени для программы";
  await user.type(screen.getByLabelText("Причина для выпускника"), reason);
  await user.click(button);
  await waitFor(() => expect(reject).toHaveBeenCalledWith("go-1", { reason }));
});

it("требует выбора возврата при отмене оплаченной консультации", async () => {
  const user = userEvent.setup();
  const cancel = vi
    .spyOn(workspaceApi, "cancelConsultation")
    .mockResolvedValue(consultation);
  openPage();
  await user.click(
    await screen.findByRole("button", { name: "Отменить заявку" }),
  );
  const dialog = screen.getAllByRole("dialog").at(-1)!;
  const reason = "Встреча не состоялась по договорённости";
  await user.type(
    within(dialog).getByLabelText("Причина для выпускника"),
    reason,
  );
  const button = within(dialog).getByRole("button", {
    name: "Подтвердить решение",
  });
  expect(button).toBeDisabled();
  await user.click(within(dialog).getByLabelText("Нужен возврат денег"));
  await user.click(button);
  await waitFor(() =>
    expect(cancel).toHaveBeenCalledWith(consultation.id, {
      reason,
      refund_required: true,
    }),
  );
});

it("передаёт выбранный этап KPI в запрос очереди и URL", async () => {
  const user = userEvent.setup();
  const result = openPage(consultation, "/admin/opportunities");
  await user.click(
    await screen.findByRole("button", { name: "Назначить время · 1" }),
  );
  expect(result.router.state.location.search).toContain("stage=needs_schedule");
  await waitFor(() =>
    expect(workspaceApi.page).toHaveBeenLastCalledWith(
      "inbox",
      expect.any(URLSearchParams),
    ),
  );
  const params = vi.mocked(workspaceApi.page).mock.calls.at(-1)![1];
  expect(params.get("stage")).toBe("needs_schedule");
});

it("показывает пустую очередь", async () => {
  openPage(consultation, "/admin/opportunities", true);
  expect(await screen.findByText("Всё разобрано")).toBeInTheDocument();
});

it.each([
  ["requested", "new", "Одобрить и выставить счёт"],
  ["payment_pending", "payment_review", "Подтвердить оплату"],
  ["paid", "needs_schedule", "Назначить время"],
  ["scheduled", "scheduled", "Перенести"],
  ["scheduled", "needs_completion", "Завершить консультацию"],
] as const)(
  "показывает одно основное действие для этапа %s / %s",
  async (status, stage, title) => {
    openPage({
      ...consultation,
      status,
      stage,
      last_payment:
        stage === "payment_review"
          ? {
              attempt_id: "payment-1",
              status: "manual_review",
              created_at: consultation.created_at,
            }
          : null,
    });
    const primary = await screen.findByRole("group", {
      name: "Основное действие",
    });
    expect(within(primary).getAllByRole("button")).toHaveLength(1);
    expect(
      within(primary).getByRole("button", { name: title }),
    ).toBeInTheDocument();
  },
);

it("подтверждает оплату из карточки", async () => {
  const user = userEvent.setup();
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const confirm = vi
    .spyOn(workspaceApi, "confirmPayment")
    .mockResolvedValue(consultation);
  openPage({
    ...consultation,
    status: "payment_pending",
    stage: "payment_review",
    last_payment: {
      attempt_id: "payment-1",
      status: "manual_review",
      created_at: consultation.created_at,
    },
  });
  await user.click(
    await screen.findByRole("button", { name: "Подтвердить оплату" }),
  );
  await waitFor(() => expect(confirm).toHaveBeenCalledWith("payment-1"));
});

it("исправляет итог отдельной командой", async () => {
  const user = userEvent.setup();
  const edit = vi
    .spyOn(workspaceApi, "summaryConsultation")
    .mockResolvedValue(consultation);
  openPage({
    ...consultation,
    status: "completed",
    stage: "completed",
    written_summary: "Сохранённые рекомендации для выпускника",
  });
  await user.click(
    await screen.findByRole("button", { name: "Исправить итог" }),
  );
  const input = screen.getByLabelText("Итог для выпускника");
  await user.clear(input);
  await user.type(input, "Исправленный план дальнейших действий");
  await user.click(
    screen.getByRole("button", { name: "Сохранить исправленный итог" }),
  );
  await waitFor(() =>
    expect(edit).toHaveBeenCalledWith(consultation.id, {
      written_summary: "Исправленный план дальнейших действий",
    }),
  );
});

it("закрывает карточку по прямой ссылке, сохраняя фильтр", async () => {
  const user = userEvent.setup();
  const result = openPage(
    consultation,
    "/admin/opportunities?stage=needs_schedule&consultation=consultation-1",
  );
  await user.click(
    await screen.findByRole("button", { name: "Закрыть заявку" }),
  );
  expect(result.router.state.location.search).not.toContain("consultation=");
  expect(result.router.state.location.search).toContain("stage=needs_schedule");
});

it("показывает переведённую причину Python и требует подтверждения отклонения", async () => {
  const user = userEvent.setup();
  const { repeatApplication } = await import("./opportunityWorkspaceFixtures");
  const item = {
    ...repeatApplication,
    status: "under_review" as const,
    stage: "review",
  };
  const transition = vi
    .spyOn(api, "transitionAdminPythonRepeat")
    .mockResolvedValue({
      applications: [{ ...item, enrollment: null, obligation: null }],
      mentors: [],
    });
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  vi.spyOn(workspaceApi, "repeat").mockResolvedValue(item);
  openPage(
    consultation,
    "/admin/opportunities/python-repeat?application=repeat-1",
  );
  expect(
    await screen.findByText("Потеря работы", { exact: false }),
  ).toBeInTheDocument();
  expect(screen.queryByText("lost_job")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Отклонить" }));
  expect(transition).not.toHaveBeenCalled();
  confirm.mockReturnValue(true);
  await user.click(screen.getByRole("button", { name: "Отклонить" }));
  await waitFor(() =>
    expect(transition).toHaveBeenCalledWith(item.id, {
      status: "rejected",
      comment: "",
      responsible_user_id: null,
    }),
  );
});

it("берёт число платежей Python из сохранённых условий", async () => {
  const { repeatApplication } = await import("./opportunityWorkspaceFixtures");
  vi.spyOn(workspaceApi, "repeat").mockResolvedValue({
    ...repeatApplication,
    status: "approved",
    stage: "awaiting_payment",
    terms_version: 1,
    terms_snapshot: {
      upfront_price_kopecks: 3000000,
      success_fee_percent: 100,
      success_fee_installments_count: 2,
    },
  });
  openPage(
    consultation,
    "/admin/opportunities/python-repeat?application=repeat-1",
  );
  expect(await screen.findByText(/число платежей: 2/)).toBeInTheDocument();
  expect(screen.queryByText(/4 платежа/)).not.toBeInTheDocument();
});

it("предпросмотр описания Go показывает черновик до сохранения", async () => {
  const user = userEvent.setup();
  const save = vi.spyOn(api, "updateAdminGoTransitionProgram");
  openPage(consultation, "/admin/opportunities/settings");
  const input = await screen.findByLabelText("Описание программы");
  await user.clear(input);
  await user.type(
    input,
    "## Черновик программы\n\nНовые детали подготовки и практики",
  );
  expect(
    await screen.findByRole("heading", { name: "Черновик программы" }),
  ).toBeInTheDocument();
  expect(save).not.toHaveBeenCalled();
});

it("кнопка Назад в Telegram закрывает карточку и возвращает корневую вкладку", async () => {
  let back: (() => void) | undefined;
  const show = vi.fn(),
    hide = vi.fn();
  (window as Window & { TelegramWebviewProxy?: unknown }).TelegramWebviewProxy =
    { postEvent: vi.fn() };
  window.Telegram = {
    WebApp: {
      initData: "query_id=test",
      colorScheme: "dark",
      ready: vi.fn(),
      expand: vi.fn(),
      onEvent: vi.fn(),
      offEvent: vi.fn(),
      close: vi.fn(),
      BackButton: {
        show,
        hide,
        onClick: (handler) => {
          back = handler;
        },
        offClick: vi.fn(),
      },
    },
  };
  vi.spyOn(api, "me").mockResolvedValue({
    id: "admin-1",
    first_name: "Админ",
    last_name: null,
    telegram_id: 1,
    email: null,
    role: "admin",
    is_active: true,
    onboarding_completed_at: "2026-10-01T00:00:00Z",
  });
  vi.spyOn(api, "notifications").mockResolvedValue({
    items: [],
    unread_count: 0,
    total: 0,
    limit: 20,
    offset: 0,
  });
  vi.spyOn(copilotApi, "access").mockResolvedValue({
    allowed: true,
    student_allowed: true,
    students_enabled: true,
    learning_status: "active",
    reason: "",
  });
  vi.spyOn(workspaceApi, "summary").mockResolvedValue({
    needs_action_total: 0,
    overdue_total: 0,
    consultations: {},
    go_transition: {},
    python_repeat: {},
  });
  const result = renderPage(
    <AppLayout />,
    "/admin/opportunities/consultations?group=all&consultation=consultation-1",
    "/admin/opportunities/*",
  );
  await waitFor(() => expect(show).toHaveBeenCalled());
  await act(async () => {
    back?.();
  });
  await waitFor(() =>
    expect(result.router.state.location.search).not.toContain("consultation="),
  );
  expect(result.router.state.location.pathname).toBe(
    "/admin/opportunities/consultations",
  );
  expect(result.router.state.location.search).toContain("group=all");
  expect(hide).toHaveBeenCalled();
});
