import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AlumniConsultationsPage } from "../src/pages/AlumniConsultationsPage";
import { AlumniOpportunitiesPage } from "../src/pages/AlumniOpportunitiesPage";
import { GoTransitionOpportunityPage } from "../src/pages/GoTransitionOpportunityPage";
import { OpportunitiesPage } from "../src/pages/OpportunitiesPage";
import type { OpportunitiesDashboard } from "../src/types/api";
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
  expect(screen.getByText("30 000 ₽")).toBeInTheDocument();
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
        created_at: "2026-08-30T00:00:00Z",
      },
    ],
  });
  renderPage(
    <GoTransitionOpportunityPage />,
    "/opportunities/alumni/go-transition",
    "/opportunities/alumni/go-transition",
  );

  const field = await screen.findByLabelText("Зачем вам Go-направление");
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
    screen.getByLabelText("Короткий бриф"),
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
