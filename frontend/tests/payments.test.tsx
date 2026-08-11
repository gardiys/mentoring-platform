import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminMentorPayoutsPanel } from "../src/components/AdminMentorPayoutsPanel";
import { PaymentSchedule } from "../src/components/PaymentSchedule";
import { AdminMentorPaymentDetailPage } from "../src/pages/AdminMentorPaymentDetailPage";
import { AdminOverduePaymentsPage } from "../src/pages/AdminOverduePaymentsPage";
import { AdminPaymentsPage } from "../src/pages/AdminPaymentsPage";
import { AdminStudentPaymentsPage } from "../src/pages/AdminStudentPaymentsPage";
import { MentorRewardsPage } from "../src/pages/MentorRewardsPage";
import { PaymentsPage } from "../src/pages/PaymentsPage";
import type {
  AdminMentorPayoutDetail,
  AdminMentorPayoutDashboard,
  AdminPaymentPage,
  AdminPaymentStudentPage,
  MentorRewardSummary,
  StudentPaymentDashboard,
} from "../src/types/api";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

const dashboard: StudentPaymentDashboard = {
  student_id: "10000000-0000-4000-8000-000000000001",
  student_name: "Иван Иванов",
  repayment_percent: 200,
  mentor_reward_percent: 40,
  employment: {
    id: "20000000-0000-4000-8000-000000000001",
    company_id: null,
    company_name: "Яндекс",
    start_date: "2026-08-12",
    net_salary_kopecks: 20_000_000,
    repayment_percent: 200,
    status: "active",
    ended_at: null,
    end_reason: null,
    payment_days: [10, 25],
    total_owed_kopecks: 40_000_000,
    created_at: "2026-08-12T10:00:00Z",
    updated_at: "2026-08-12T10:00:00Z",
  },
  installments: [
    {
      id: "30000000-0000-4000-8000-000000000001",
      sequence_number: 1,
      due_date: "2026-09-25",
      amount_kopecks: 5_000_000,
      salary_percent: 25,
      employment_id: "20000000-0000-4000-8000-000000000001",
      company_name: "Яндекс",
      status: "scheduled",
      paid_at: null,
      revoked_at: null,
      revocation_reason: null,
      payment_url: null,
      can_pay: true,
    },
  ],
  summary: {
    total_owed_kopecks: 40_000_000,
    paid_kopecks: 0,
    remaining_kopecks: 40_000_000,
    overdue_kopecks: 0,
    paid_installments: 0,
    total_installments: 8,
    paid_salary_percent: 0,
    remaining_salary_percent: 200,
  },
  employment_history: [],
  can_manage_employment: false,
  can_manage_payment_days: true,
};

const admin = {
  id: "10000000-0000-4000-8000-000000000099",
  telegram_id: 999,
  first_name: "Администратор",
  last_name: null,
  email: "admin@example.com",
  role: "admin" as const,
  onboarding_completed_at: "2026-08-01T00:00:00Z",
  is_active: true,
};

function mockAdminPaymentCheck() {
  vi.spyOn(api, "me").mockResolvedValue(admin);
  vi.spyOn(api, "adminTochkaTestPayment").mockResolvedValue(null);
}

it("показывает график и сохраняет ровно две выбранные даты", async () => {
  const save = vi.fn().mockResolvedValue(undefined);
  renderPage(<PaymentSchedule dashboard={dashboard} onSaveDays={save} />);

  expect(screen.getAllByText("Яндекс")).toHaveLength(2);
  expect(screen.getAllByText("400 000 ₽")).toHaveLength(2);
  expect(screen.getByText("50 000 ₽")).toBeInTheDocument();

  const first = screen.getByLabelText("Первый день");
  const second = screen.getByLabelText("Второй день");
  await userEvent.clear(first);
  await userEvent.type(first, "5");
  await userEvent.clear(second);
  await userEvent.type(second, "20");
  await userEvent.click(screen.getByRole("button", { name: "Сохранить даты" }));

  expect(save).toHaveBeenCalledWith([5, 20]);
});

it("ученик сохраняет email перед созданием платёжной ссылки", async () => {
  const student = { ...admin, role: "student" as const, email: null };
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "myPayments").mockResolvedValue(dashboard);
  const updateEmail = vi.spyOn(api, "updateMyEmail").mockResolvedValue({
    ...student,
    email: "student@example.com",
  });

  renderPage(<PaymentsPage />, "/payments", "/payments");

  expect(
    await screen.findByText("Укажите email перед оплатой"),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Оплатить" }),
  ).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Email"), "student@example.com");
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить email" }),
  );

  await waitFor(() =>
    expect(updateEmail).toHaveBeenCalledWith(
      "student@example.com",
      expect.anything(),
    ),
  );
  expect(
    await screen.findByRole("button", { name: "Оплатить" }),
  ).toBeInTheDocument();
});

const studentRegistry: AdminPaymentStudentPage = {
  items: [
    {
      employment_id: dashboard.employment!.id,
      student_id: dashboard.student_id,
      student_name: dashboard.student_name,
      student_telegram_username: "ivan",
      mentor_id: "10000000-0000-4000-8000-000000000010",
      mentor_name: "Антон",
      company_name: "Яндекс",
      employment_start_date: "2026-08-12",
      net_salary_kopecks: 20_000_000,
      repayment_percent: 200,
      total_owed_kopecks: 40_000_000,
      paid_kopecks: 5_000_000,
      remaining_kopecks: 35_000_000,
      overdue_kopecks: 5_000_000,
      overdue_payments: 1,
      next_payment_date: "2026-09-25",
      paid_installments: 1,
      total_installments: 8,
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
  total_remaining_kopecks: 35_000_000,
  total_paid_kopecks: 5_000_000,
  total_overdue_kopecks: 5_000_000,
};

it("показывает учеников с офферами вместо плоского списка взносов", async () => {
  mockAdminPaymentCheck();
  vi.spyOn(api, "adminPaymentStudents").mockResolvedValue(studentRegistry);

  renderPage(<AdminPaymentsPage />);

  expect(await screen.findByText("Иван Иванов")).toBeInTheDocument();
  expect(screen.getAllByText("350 000 ₽")).toHaveLength(2);
  expect(screen.getByRole("link", { name: "Открыть платежи" })).toHaveAttribute(
    "href",
    `/admin/payments/students/${dashboard.student_id}`,
  );
});

it("переключает реестр на полностью выплаченные офферы", async () => {
  mockAdminPaymentCheck();
  const registry = vi
    .spyOn(api, "adminPaymentStudents")
    .mockResolvedValue(studentRegistry);

  renderPage(<AdminPaymentsPage />);

  await screen.findByText("Иван Иванов");
  await userEvent.click(screen.getByText("Выплачены"));

  await waitFor(() =>
    expect(registry).toHaveBeenCalledWith({
      status: "paid",
      limit: 50,
      offset: 0,
    }),
  );
});

it("создаёт для администратора изолированную тестовую оплату на 10 рублей", async () => {
  mockAdminPaymentCheck();
  vi.spyOn(api, "adminPaymentStudents").mockResolvedValue(studentRegistry);
  const create = vi
    .spyOn(api, "createAdminTochkaTestPayment")
    .mockResolvedValue({
      id: "90000000-0000-4000-8000-000000000001",
      amount_kopecks: 1_000,
      status: "pending",
      payment_url: "https://secure.tochka.test/payment",
      provider_operation_id: null,
      approved_at: null,
      created_at: "2026-08-12T12:00:00Z",
    });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const replace = vi.fn();
  vi.spyOn(window, "open").mockReturnValue({
    opener: null,
    closed: false,
    location: { replace },
  } as unknown as Window);

  renderPage(<AdminPaymentsPage />);

  expect(
    await screen.findByDisplayValue("admin@example.com"),
  ).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Создать тестовую оплату · 10 ₽" }),
  );

  await waitFor(() =>
    expect(create).toHaveBeenCalledWith("admin@example.com", expect.anything()),
  );
  await waitFor(() =>
    expect(replace).toHaveBeenCalledWith("https://secure.tochka.test/payment"),
  );
});

it("администратор переносит отдельный платёж с указанием причины", async () => {
  vi.spyOn(api, "adminPaymentStudent").mockResolvedValue(dashboard);
  const reschedule = vi.spyOn(api, "rescheduleAdminPayment").mockResolvedValue({
    ...dashboard,
    installments: [
      {
        ...dashboard.installments[0]!,
        due_date: "2026-10-05",
        due_date_changed_at: "2026-08-12T12:00:00Z",
        previous_due_date: "2026-09-25",
        due_date_change_reason: "Перенос по просьбе ученика",
      },
    ],
  });

  renderPage(
    <AdminStudentPaymentsPage />,
    `/admin/payments/students/${dashboard.student_id}`,
    "/admin/payments/students/:studentId",
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "Перенести дату" }),
  );
  const dueDate = await screen.findByLabelText(/Новая дата платежа/);
  await userEvent.clear(dueDate);
  await userEvent.type(dueDate, "2026-10-05");
  await userEvent.type(
    await screen.findByLabelText(/Причина переноса/),
    "Перенос по просьбе ученика",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Перенести платёж" }),
  );

  await waitFor(() =>
    expect(reschedule).toHaveBeenCalledWith(dashboard.installments[0]!.id, {
      due_date: "2026-10-05",
      reason: "Перенос по просьбе ученика",
    }),
  );
});

it("администратор отменяет ошибочно подтверждённый платёж с причиной", async () => {
  const paidDashboard: StudentPaymentDashboard = {
    ...dashboard,
    installments: [
      {
        ...dashboard.installments[0]!,
        status: "paid",
        paid_at: "2026-09-25T12:00:00Z",
        can_pay: false,
      },
    ],
  };
  vi.spyOn(api, "adminPaymentStudent").mockResolvedValue(paidDashboard);
  const revoke = vi
    .spyOn(api, "revokeAdminPayment")
    .mockResolvedValue(dashboard);

  renderPage(
    <AdminStudentPaymentsPage />,
    `/admin/payments/students/${dashboard.student_id}`,
    "/admin/payments/students/:studentId",
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "Отменить подтверждение" }),
  );
  await userEvent.type(
    await screen.findByRole("textbox", { name: /Причина отмены/ }),
    "Подтверждено ошибочно",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Отменить платёж" }),
  );

  await waitFor(() =>
    expect(revoke).toHaveBeenCalledWith(
      dashboard.installments[0]!.id,
      "Подтверждено ошибочно",
    ),
  );
});

const overduePage: AdminPaymentPage = {
  items: [
    {
      installment_id: dashboard.installments[0]!.id,
      student_id: dashboard.student_id,
      student_name: dashboard.student_name,
      student_telegram_username: "ivan",
      mentor_id: "10000000-0000-4000-8000-000000000010",
      mentor_name: "Антон",
      company_name: "Яндекс",
      due_date: "2025-09-25",
      amount_kopecks: 5_000_000,
      status: "scheduled",
      paid_at: null,
      mentor_reward_kopecks: null,
      mentor_reward_id: null,
      mentor_reward_paid_at: null,
      requires_manual_review: false,
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
  scheduled_kopecks: 5_000_000,
  paid_kopecks: 0,
  overdue_kopecks: 5_000_000,
  mentor_rewards_accrued_kopecks: 0,
  mentor_rewards_paid_kopecks: 0,
  mentor_rewards: [],
};

it("выносит все просроченные платежи в отдельный реестр", async () => {
  vi.spyOn(api, "adminOverduePayments").mockResolvedValue(overduePage);

  renderPage(<AdminOverduePaymentsPage />);

  expect(await screen.findByText("Иван Иванов")).toBeInTheDocument();
  expect(screen.getAllByText("50 000 ₽").length).toBeGreaterThan(0);
  expect(screen.getByRole("link", { name: "Открыть ученика" })).toHaveAttribute(
    "href",
    `/admin/payments/students/${dashboard.student_id}`,
  );
});

const payoutDashboard: AdminMentorPayoutDashboard = {
  balances: [
    {
      mentor_id: "10000000-0000-4000-8000-000000000010",
      mentor_name: "Антон",
      mentor_telegram_username: "mentor",
      accrued_kopecks: 3_000_000,
      paid_kopecks: 500_000,
      reserved_kopecks: 500_000,
      available_kopecks: 2_000_000,
    },
  ],
  payouts: [
    {
      id: "40000000-0000-4000-8000-000000000001",
      mentor_id: "10000000-0000-4000-8000-000000000010",
      mentor_name: "Антон",
      mentor_telegram_username: "mentor",
      amount_kopecks: 500_000,
      origin: "mentor_request",
      status: "requested",
      payment_reference: null,
      created_at: "2026-08-10T10:00:00Z",
      paid_at: null,
      cancelled_at: null,
      cancellation_reason: null,
      edited_at: null,
      edit_reason: null,
      receipt_filename: null,
      receipt_content_type: null,
      receipt_size: null,
      receipt_uploaded_at: null,
    },
  ],
};

it("администратор выплачивает часть общего баланса ментора", async () => {
  vi.spyOn(api, "adminMentorPayouts").mockResolvedValue(payoutDashboard);
  const create = vi
    .spyOn(api, "createAdminMentorPayout")
    .mockResolvedValue(payoutDashboard);
  vi.spyOn(window, "confirm").mockReturnValue(true);

  renderPage(<AdminMentorPayoutsPanel />);
  expect(await screen.findByText("Доступно")).toBeInTheDocument();
  await userEvent.type(
    screen.getByLabelText("Сумма частичной выплаты, ₽"),
    "12000",
  );
  await userEvent.type(
    screen.getAllByLabelText("Номер акта / комментарий")[1]!,
    "Акт №12",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Выплатить сумму" }),
  );

  await waitFor(() =>
    expect(create).toHaveBeenCalledWith(
      "10000000-0000-4000-8000-000000000010",
      { amount_rubles: 12_000, payment_reference: "Акт №12" },
    ),
  );
});

const mentorSummary: MentorRewardSummary = {
  mentor_id: "10000000-0000-4000-8000-000000000010",
  accrued_kopecks: 2_000_000,
  paid_kopecks: 500_000,
  unpaid_kopecks: 1_500_000,
  reserved_kopecks: 0,
  available_kopecks: 1_500_000,
  rewards: [],
  payouts: [
    {
      id: "40000000-0000-4000-8000-000000000002",
      mentor_id: "10000000-0000-4000-8000-000000000010",
      mentor_name: "Антон",
      mentor_telegram_username: "mentor",
      amount_kopecks: 500_000,
      origin: "admin_direct",
      status: "paid",
      payment_reference: "Акт №10",
      created_at: "2026-08-10T10:00:00Z",
      paid_at: "2026-08-10T11:00:00Z",
      cancelled_at: null,
      cancellation_reason: null,
      edited_at: null,
      edit_reason: null,
      receipt_filename: null,
      receipt_content_type: null,
      receipt_size: null,
      receipt_uploaded_at: null,
    },
  ],
};

const mentorDetail: AdminMentorPayoutDetail = {
  mentor_id: mentorSummary.mentor_id,
  mentor_name: "Антон",
  mentor_telegram_username: "mentor",
  accrued_kopecks: 2_000_000,
  paid_kopecks: 500_000,
  reserved_kopecks: 0,
  available_kopecks: 1_500_000,
  rewards: [
    {
      id: "50000000-0000-4000-8000-000000000001",
      kind: "employment_payment",
      mentor_id: mentorSummary.mentor_id,
      mentor_name: "Антон",
      mentor_telegram_username: "mentor",
      student_id: dashboard.student_id,
      student_name: dashboard.student_name,
      student_telegram_username: "ivan",
      company_name: "Яндекс",
      basis_kopecks: 5_000_000,
      reward_percent: 40,
      amount_kopecks: 1_000_000,
      paid_kopecks: 0,
      reserved_kopecks: 0,
      available_kopecks: 1_000_000,
      created_at: "2026-09-25T12:00:00Z",
      paid_at: null,
    },
  ],
  payouts: mentorSummary.payouts,
};

it("показывает администратору происхождение начислений конкретного ментора", async () => {
  vi.spyOn(api, "adminMentorPayoutDetail").mockResolvedValue(mentorDetail);

  renderPage(
    <AdminMentorPaymentDetailPage />,
    `/admin/payments/mentors/${mentorDetail.mentor_id}`,
    "/admin/payments/mentors/:mentorId",
  );

  expect(
    await screen.findByText("Из чего сложилась сумма"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Платёж после трудоустройства · Яндекс"),
  ).toBeInTheDocument();
  expect(screen.getByText("Иван Иванов")).toBeInTheDocument();
  expect(screen.getByText("50 000 ₽")).toBeInTheDocument();
});

it("администратор удаляет повторное архивное начисление из баланса ментора", async () => {
  vi.spyOn(api, "adminMentorPayoutDetail").mockResolvedValue(mentorDetail);
  const voidReward = vi
    .spyOn(api, "voidAdminMentorReward")
    .mockResolvedValue(payoutDashboard);

  renderPage(
    <AdminMentorPaymentDetailPage />,
    `/admin/payments/mentors/${mentorDetail.mentor_id}`,
    "/admin/payments/mentors/:mentorId",
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "Удалить ошибочное" }),
  );
  const dialog = await screen.findByRole("dialog");
  const submit = within(dialog).getByRole("button", {
    name: "Удалить начисление",
  });
  expect(submit).toBeDisabled();
  await userEvent.type(
    within(dialog).getByRole("textbox", { name: /Причина удаления/ }),
    "Расчёт по архиву уже закрыт",
  );
  await userEvent.click(submit);

  await waitFor(() =>
    expect(voidReward).toHaveBeenCalledWith(
      "50000000-0000-4000-8000-000000000001",
      "Расчёт по архиву уже закрыт",
    ),
  );
});

it("администратор редактирует зафиксированную выплату ментора", async () => {
  vi.spyOn(api, "adminMentorPayoutDetail").mockResolvedValue(mentorDetail);
  const edit = vi
    .spyOn(api, "editAdminMentorPayout")
    .mockResolvedValue(payoutDashboard);

  renderPage(
    <AdminMentorPaymentDetailPage />,
    `/admin/payments/mentors/${mentorDetail.mentor_id}`,
    "/admin/payments/mentors/:mentorId",
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "Редактировать" }),
  );
  const dialog = await screen.findByRole("dialog");
  const amount = within(dialog).getByRole("textbox", {
    name: /Сумма выплаты/,
  });
  await userEvent.clear(amount);
  await userEvent.type(amount, "4000");
  await userEvent.type(
    within(dialog).getByRole("textbox", { name: /Причина изменения/ }),
    "Исправлена сумма в акте",
  );
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Сохранить изменения" }),
  );

  await waitFor(() =>
    expect(edit).toHaveBeenCalledWith(
      "40000000-0000-4000-8000-000000000002",
      expect.objectContaining({
        amount_rubles: 4_000,
        payment_reference: "Акт №10",
        reason: "Исправлена сумма в акте",
      }),
    ),
  );
});

it("администратор удаляет ошибочную выплату с обязательной причиной", async () => {
  vi.spyOn(api, "adminMentorPayoutDetail").mockResolvedValue(mentorDetail);
  const cancel = vi
    .spyOn(api, "cancelAdminMentorPayout")
    .mockResolvedValue(payoutDashboard);

  renderPage(
    <AdminMentorPaymentDetailPage />,
    `/admin/payments/mentors/${mentorDetail.mentor_id}`,
    "/admin/payments/mentors/:mentorId",
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "Удалить ошибочную" }),
  );
  const dialog = await screen.findByRole("dialog");
  const submit = within(dialog).getByRole("button", {
    name: "Удалить ошибочную",
  });
  expect(submit).toBeDisabled();
  await userEvent.type(
    within(dialog).getByRole("textbox", { name: /Причина отмены/ }),
    "Выплата создана случайно",
  );
  await userEvent.click(submit);

  await waitFor(() =>
    expect(cancel).toHaveBeenCalledWith(
      "40000000-0000-4000-8000-000000000002",
      "Выплата создана случайно",
    ),
  );
});

it("ментор запрашивает выплату и может приложить необязательный чек", async () => {
  vi.spyOn(api, "mentorRewards").mockResolvedValue(mentorSummary);
  const request = vi
    .spyOn(api, "requestMentorPayout")
    .mockResolvedValue(mentorSummary);
  const upload = vi
    .spyOn(api, "uploadMentorPayoutReceipt")
    .mockResolvedValue(mentorSummary);

  renderPage(<MentorRewardsPage />);
  await userEvent.type(await screen.findByLabelText("Сумма, ₽"), "10000");
  await userEvent.click(
    screen.getByRole("button", { name: "Отправить заявку" }),
  );
  await waitFor(() => expect(request).toHaveBeenCalledWith(10_000));

  const receipt = new File(["receipt"], "receipt.pdf", {
    type: "application/pdf",
  });
  const receiptInput =
    document.querySelector<HTMLInputElement>('input[type="file"]');
  expect(receiptInput).not.toBeNull();
  await userEvent.upload(receiptInput!, receipt);
  await userEvent.click(screen.getByRole("button", { name: "Загрузить" }));
  await waitFor(() =>
    expect(upload).toHaveBeenCalledWith(
      "40000000-0000-4000-8000-000000000002",
      receipt,
      expect.objectContaining({ signal: expect.any(AbortSignal) }),
    ),
  );
});
