import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AlumniConsultationsPage } from "../src/pages/AlumniConsultationsPage";
import { AlumniOpportunitiesPage } from "../src/pages/AlumniOpportunitiesPage";
import { GoTransitionOpportunityPage } from "../src/pages/GoTransitionOpportunityPage";
import { OpportunitiesPage } from "../src/pages/OpportunitiesPage";
import { PythonRepeatOpportunityPage } from "../src/pages/PythonRepeatOpportunityPage";
import type {
  OpportunitiesDashboard,
  PythonRepeatDashboard,
} from "../src/types/api";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

const student = {
  id: "10000000-0000-4000-8000-000000000001",
  telegram_id: 1,
  first_name: "Иван",
  last_name: null,
  email: "student@example.com",
  role: "student" as const,
  onboarding_completed_at: "2026-08-01T00:00:00Z",
  is_active: true,
};

const dashboard: OpportunitiesDashboard = {
  opportunities_enabled: true,
  consultations_enabled: true,
  python_repeat_mentorship_enabled: true,
  python_to_go_enabled: true,
  segment: "PYTHON_ALUMNI",
  has_active_program: false,
  has_alumni_access: true,
  opportunities: [
    {
      code: "ALUMNI_CONSULTATION",
      available: true,
      title: "Консультация с ментором",
      unavailable_reason: null,
      price: { amount_kopecks: 400_000, currency: "RUB" },
      comparison_price: { amount_kopecks: 500_000, currency: "RUB" },
      upfront_price_kopecks: null,
      success_fee_percent: null,
      comparison_upfront_price_kopecks: null,
      comparison_success_fee_percent: null,
    },
    {
      code: "PYTHON_REPEAT_MENTORSHIP",
      available: true,
      title: "Повторное менторство по Python",
      unavailable_reason: null,
      price: null,
      comparison_price: null,
      upfront_price_kopecks: 3_000_000,
      success_fee_percent: 100,
      comparison_upfront_price_kopecks: null,
      comparison_success_fee_percent: null,
    },
    {
      code: "PYTHON_TO_GO_ALUMNI",
      available: true,
      title: "Переход Python → Go",
      unavailable_reason: null,
      price: null,
      comparison_price: null,
      upfront_price_kopecks: 3_000_000,
      success_fee_percent: 100,
      comparison_upfront_price_kopecks: 4_500_000,
      comparison_success_fee_percent: 150,
    },
  ],
  mentors: [
    {
      id: "20000000-0000-4000-8000-000000000001",
      first_name: "Антон",
      last_name: "Ментор",
      telegram_username: "mentor",
    },
  ],
  consultation_types: [
    {
      code: "free_topic",
      title: "Свободная тема",
      description: "Разберите любой вопрос с ментором.",
      price_kopecks: 400_000,
      comparison_price_kopecks: 500_000,
      mentor_reward_kopecks: 250_000,
      duration_minutes: 60,
    },
    {
      code: "technical_mock",
      title: "Техническое мок-собеседование",
      description: "Репетиция технического интервью.",
      price_kopecks: 400_000,
      comparison_price_kopecks: 500_000,
      mentor_reward_kopecks: 250_000,
      duration_minutes: 60,
    },
    {
      code: "work_task",
      title: "Помощь с рабочей задачей",
      description: "Разбор сложной рабочей задачи.",
      price_kopecks: 600_000,
      comparison_price_kopecks: 700_000,
      mentor_reward_kopecks: 300_000,
      duration_minutes: 90,
    },
  ],
  go_transition_description_markdown:
    "## Что входит в программу\n\n- Go и конкурентность\n- Backend-практика",
  consultations: [],
  go_transition_applications: [],
};

const pythonRepeatDashboard: PythonRepeatDashboard = {
  enabled: true,
  eligibility: {
    eligible: true,
    code: "eligible",
    message: "Можно подать заявку",
    override_allowed: false,
  },
  product: {
    product_code: "PYTHON_REPEAT_MENTORSHIP",
    terms_version: 3,
    upfront_price_kopecks: 3_000_000,
    success_fee_percent: 100,
    success_fee_installments_count: 2,
    active_support_months: 3,
    probation_support_days: 90,
    included_mock_interviews: 2,
    offer_valid_days: 14,
    public_offer_revision: "02.09.2026",
    public_offer_published_at: "2026-09-02",
    public_offer_url: "/legal/python-repeat-mentorship-offer-2026-09-02.pdf",
    public_offer_sha256:
      "2f7a2c4e01609f37a9ebb04b7c93943d4f616cb2f55691ec409d41e9270bbd3f",
    acceptance_statement: "Я ознакомился и полностью принимаю Публичную оферту",
  },
  application: null,
  enrollment: null,
  offers: [],
  obligation: null,
};

const pythonRepeatDraftDashboard: PythonRepeatDashboard = {
  ...pythonRepeatDashboard,
  application: {
    id: "60000000-0000-4000-8000-000000000001",
    student_id: student.id,
    employment_status: "employed",
    reason: "wants_higher_salary",
    current_position: "Python-разработчик",
    current_company: "Компания",
    current_stack: "Python",
    last_interview_at: null,
    target_position: "Python Backend Developer",
    target_salary_kopecks: 25_000_000,
    technical_gaps: "Хочу системно повторить Python и архитектуру",
    hours_per_week: 10,
    desired_start_date: null,
    search_mode: "search_while_employed",
    additional_comment: null,
    status: "draft",
    responsible_user_id: null,
    eligibility_override_reason: null,
    admin_comment: null,
    terms_version: null,
    terms_snapshot: null,
    approved_at: null,
    offer_expires_at: null,
    accepted_at: null,
    acceptance_evidence: null,
    contract_accepted_at: null,
    acceptance_payment_link_id: null,
    acceptance_provider_operation_id: null,
    paid_at: null,
    created_at: "2026-09-01T00:00:00Z",
    history: [],
  },
};

it("показывает кабинет выпускника отдельным подразделом возможностей", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "myOpportunities").mockResolvedValue(dashboard);
  renderPage(<OpportunitiesPage />, "/opportunities", "/opportunities");

  expect(await screen.findByText("Кабинет выпускника")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Открыть кабинет выпускника" }),
  ).toHaveAttribute("href", "/opportunities/alumni");
});

it("показывает действующему ученику кабинет выпускника только для чтения", async () => {
  const activeDashboard: OpportunitiesDashboard = {
    ...dashboard,
    segment: "ACTIVE_STUDENT",
    has_active_program: true,
    has_alumni_access: false,
    opportunities: dashboard.opportunities.map((item) => ({
      ...item,
      available: false,
      unavailable_reason: "Доступно после завершения программы",
    })),
  };
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "myOpportunities").mockResolvedValue(activeDashboard);

  const root = renderPage(
    <OpportunitiesPage />,
    "/opportunities",
    "/opportunities",
  );
  expect(
    await screen.findByRole("link", {
      name: "Посмотреть кабинет выпускника",
    }),
  ).toHaveAttribute("href", "/opportunities/alumni");
  root.unmount();

  renderPage(
    <AlumniOpportunitiesPage />,
    "/opportunities/alumni",
    "/opportunities/alumni",
  );
  expect(await screen.findByText("Режим просмотра")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Посмотреть форматы консультаций" }),
  ).toBeInTheDocument();
});

it("показывает выпускнику рассчитанные backend специальные цены", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "myOpportunities").mockResolvedValue(dashboard);
  renderPage(
    <AlumniOpportunitiesPage />,
    "/opportunities/alumni",
    "/opportunities/alumni",
  );

  expect(await screen.findByText("Кабинет выпускника")).toBeInTheDocument();
  expect(screen.getAllByText("4 000 ₽")).toHaveLength(1);
  expect(screen.getAllByText("30 000 ₽")).toHaveLength(2);
  expect(
    screen.getByRole("link", { name: "Подробнее и подать заявку" }),
  ).toHaveAttribute("href", "/opportunities/alumni/python-repeat");
  expect(
    screen.getByRole("link", { name: "Посмотреть форматы консультаций" }),
  ).toHaveAttribute("href", "/opportunities/alumni/consultations");
});

it("отправляет заявку на переход с введенной мотивацией", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "myOpportunities").mockResolvedValue(dashboard);
  const create = vi.spyOn(api, "createGoTransition").mockResolvedValue({
    ...dashboard,
    go_transition_applications: [
      {
        id: "30000000-0000-4000-8000-000000000001",
        motivation: "Хочу развиваться в Go backend",
        status: "submitted",
        upfront_price_kopecks: 3_000_000,
        success_fee_percent: 100,
        approved_at: null,
        terms_accepted_at: null,
        paid_at: null,
        admin_note: null,
        terms_version: 1,
        terms_snapshot: {
          product_code: "PYTHON_TO_GO_ALUMNI",
          upfront_price_kopecks: 3_000_000,
          success_fee_percent: 100,
        },
        terms_expires_at: null,
        accepted_terms_snapshot: null,
        created_at: "2026-08-30T00:00:00Z",
      },
    ],
  });
  renderPage(
    <GoTransitionOpportunityPage />,
    "/opportunities/alumni/go-transition",
    "/opportunities/alumni/go-transition",
  );

  const field = await screen.findByLabelText(/Зачем вам Go-направление/);
  await userEvent.type(field, "Хочу развиваться в Go backend");
  await userEvent.click(screen.getByRole("button", { name: "Подать заявку" }));
  await waitFor(() =>
    expect(create).toHaveBeenCalledWith(
      { motivation: "Хочу развиваться в Go backend" },
      expect.anything(),
    ),
  );
});

it("по умолчанию отправляет консультацию любому ментору с выбранным типом", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "myOpportunities").mockResolvedValue(dashboard);
  const create = vi
    .spyOn(api, "createConsultation")
    .mockResolvedValue(dashboard);
  renderPage(
    <AlumniConsultationsPage />,
    "/opportunities/alumni/consultations",
    "/opportunities/alumni/consultations",
  );

  expect(await screen.findByDisplayValue("Любой ментор")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("radio", { name: /Техническое мок-собеседование/ }),
  );
  await userEvent.type(
    screen.getByLabelText(/Короткий бриф/),
    "Хочу проверить знания Python перед интервью",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Отправить заявку" }),
  );

  await waitFor(() =>
    expect(create).toHaveBeenCalledWith(
      {
        mentor_id: null,
        consultation_type: "technical_mock",
        brief: "Хочу проверить знания Python перед интервью",
      },
      expect.anything(),
    ),
  );
});

it("показывает повышенную цену у премиального формата", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "myOpportunities").mockResolvedValue(dashboard);
  renderPage(
    <AlumniConsultationsPage />,
    "/opportunities/alumni/consultations",
    "/opportunities/alumni/consultations",
  );

  expect(
    await screen.findByText("Помощь с рабочей задачей"),
  ).toBeInTheDocument();
  expect(screen.getByText("6 000 ₽")).toBeInTheDocument();
  expect(screen.getByText("7 000 ₽")).toBeInTheDocument();
});

it("явно объясняет, почему оплата консультации недоступна без email", async () => {
  vi.spyOn(api, "me").mockResolvedValue({ ...student, email: null });
  vi.spyOn(api, "myOpportunities").mockResolvedValue({
    ...dashboard,
    consultations: [
      {
        id: "40000000-0000-4000-8000-000000000001",
        mentor: null,
        consultation_type: "free_topic",
        brief: "Нужно разобрать дальнейший карьерный план",
        price_kopecks: 400_000,
        duration_minutes: 60,
        status: "payment_pending",
        scheduled_at: null,
        paid_at: null,
        completed_at: null,
        admin_note: null,
        written_summary: null,
        created_at: "2026-08-30T00:00:00Z",
      },
    ],
  });
  renderPage(
    <AlumniConsultationsPage />,
    "/opportunities/alumni/consultations",
    "/opportunities/alumni/consultations",
  );

  expect(await screen.findByText("Нужен email для чека")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Указать email" })).toHaveAttribute(
    "href",
    "/payments",
  );
  expect(screen.getByRole("button", { name: /Оплатить/ })).toBeDisabled();
});

it("показывает зафиксированные условия Go-заявки, а не текущий тариф", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "myOpportunities").mockResolvedValue({
    ...dashboard,
    go_transition_applications: [
      {
        id: "50000000-0000-4000-8000-000000000001",
        motivation: "Хочу перейти на Go backend",
        status: "approved",
        upfront_price_kopecks: 2_500_000,
        success_fee_percent: 75,
        approved_at: "2026-08-31T00:00:00Z",
        terms_accepted_at: null,
        paid_at: null,
        admin_note: null,
        terms_version: 7,
        terms_snapshot: {
          product_code: "PYTHON_TO_GO_ALUMNI",
          upfront_price_kopecks: 2_500_000,
          success_fee_percent: 75,
        },
        terms_expires_at: "2099-09-15T12:00:00Z",
        accepted_terms_snapshot: null,
        created_at: "2026-08-30T00:00:00Z",
      },
    ],
  });
  renderPage(
    <GoTransitionOpportunityPage />,
    "/opportunities/alumni/go-transition",
    "/opportunities/alumni/go-transition",
  );

  expect(
    await screen.findByText("Зафиксированные условия · версия 7"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("25 000 ₽ + 75% после Go-оффера"),
  ).toBeInTheDocument();
});

it("выделяет выбранный формат консультации целиком", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "myOpportunities").mockResolvedValue(dashboard);
  renderPage(
    <AlumniConsultationsPage />,
    "/opportunities/alumni/consultations",
    "/opportunities/alumni/consultations",
  );

  const option = await screen.findByRole("radio", {
    name: /Техническое мок-собеседование/,
  });
  await userEvent.click(option);

  expect(option.closest(".opportunity-choice")).toHaveAttribute(
    "data-selected",
    "true",
  );
});

it("отправляет заявку повторного менторства без внутренних полей формы", async () => {
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "myPythonRepeat").mockResolvedValue(pythonRepeatDashboard);
  const create = vi
    .spyOn(api, "createPythonRepeatApplication")
    .mockResolvedValue(pythonRepeatDraftDashboard);
  const submit = vi
    .spyOn(api, "submitPythonRepeatApplication")
    .mockResolvedValue(pythonRepeatDraftDashboard);
  renderPage(
    <PythonRepeatOpportunityPage />,
    "/opportunities/alumni/python-repeat",
    "/opportunities/alumni/python-repeat",
  );

  await userEvent.type(
    await screen.findByLabelText(/Какие пробелы хотите закрыть/),
    "Хочу системно повторить Python и архитектуру",
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Отправить заявку" }),
  );

  await waitFor(() => expect(create).toHaveBeenCalled());
  const payload = create.mock.calls[0]?.[0];
  expect(payload).toBeDefined();
  expect(payload).toMatchObject({
    target_position: "Python Backend Developer",
    target_salary_kopecks: 25_000_000,
    technical_gaps: "Хочу системно повторить Python и архитектуру",
  });
  expect(payload).not.toHaveProperty("target_salary_rubles");
  await waitFor(() =>
    expect(submit).toHaveBeenCalledWith(
      pythonRepeatDraftDashboard.application?.id,
      expect.anything(),
    ),
  );
});

it("показывает оферту и передает ее неизменяемую редакцию при подтверждении", async () => {
  const statement =
    "Я ознакомился и полностью принимаю Публичную оферту на оказание информационно-консультационных услуг по программе повторного менторства по Python-разработке в редакции от 02.09.2026. Я понимаю, что стоимость услуг составляет 30 000 ₽ предоплаты и дополнительно 100% расчетного ежемесячного вознаграждения при новом трудоустройстве, выплачиваемые двумя равными платежами.";
  const approvedDashboard: PythonRepeatDashboard = {
    ...pythonRepeatDashboard,
    application: {
      ...pythonRepeatDraftDashboard.application!,
      status: "approved",
      terms_version: 3,
      terms_snapshot: {
        ...pythonRepeatDashboard.product,
        currency: "RUB",
        acceptance_statement: statement,
      },
      approved_at: "2026-09-02T09:00:00Z",
      offer_expires_at: "2099-09-16T09:00:00Z",
    },
  };
  vi.spyOn(api, "me").mockResolvedValue(student);
  vi.spyOn(api, "myPythonRepeat").mockResolvedValue(approvedDashboard);
  const accept = vi
    .spyOn(api, "acceptPythonRepeatTerms")
    .mockResolvedValue(approvedDashboard);
  renderPage(
    <PythonRepeatOpportunityPage />,
    "/opportunities/alumni/python-repeat",
    "/opportunities/alumni/python-repeat",
  );

  expect(
    await screen.findByRole("link", { name: "Открыть Публичную оферту (PDF)" }),
  ).toHaveAttribute(
    "href",
    "/legal/python-repeat-mentorship-offer-2026-09-02.pdf",
  );
  expect(screen.getByText(/Формула общей стоимости/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("checkbox", { name: statement }));
  await userEvent.click(
    screen.getByRole("button", {
      name: "Подтвердить ознакомление с офертой",
    }),
  );

  await waitFor(() =>
    expect(accept).toHaveBeenCalledWith(
      {
        id: approvedDashboard.application?.id,
        accepted: true,
        terms_version: 3,
        public_offer_revision: "02.09.2026",
        public_offer_sha256:
          "2f7a2c4e01609f37a9ebb04b7c93943d4f616cb2f55691ec409d41e9270bbd3f",
        acceptance_statement: statement,
      },
      expect.anything(),
    ),
  );
});
