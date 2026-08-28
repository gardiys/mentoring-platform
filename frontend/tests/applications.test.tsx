import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminApplicationsPage } from "../src/pages/AdminApplicationsPage";
import type {
  OnboardingApplicationDetail,
  OnboardingApplicationPage,
} from "../src/types/api";
import { renderPage } from "./render";

const application: OnboardingApplicationDetail = {
  applicant_id: "app_123",
  status: "QUALIFICATION_REVIEW_REQUIRED",
  name: "Иван Петров",
  telegram_user_id: 123456,
  telegram_username: "student",
  email: "student@example.com",
  direction: "Python",
  city: "Москва",
  admin_comment: null,
  booking_start_time: null,
  payment_status: null,
  created_at: "2026-08-18T10:00:00Z",
  updated_at: "2026-08-18T11:00:00Z",
  available_actions: [
    "approve_qualification",
    "reject_qualification",
    "defer_candidate",
    "rollback_status",
  ],
  rollback_status: "QUALIFICATION_COMPLETED",
  age: "25",
  initial_knowledge: "Проходил курс по Python",
  life_difficulties: "Нет",
  study_time_per_day: "2-3 часа",
  military_document_status: "Да",
  referral_source: "YouTube",
  form_answers: {},
  form_answer_source: "none",
  form_state: null,
  form_complete: false,
  form_missing_fields: [],
  form_documents: {},
  bookings: [],
  payments: [],
  events: [
    {
      event_type: "status_changed",
      old_status: "QUALIFICATION_COMPLETED",
      new_status: "QUALIFICATION_REVIEW_REQUIRED",
      source: "SYSTEM",
      payload: null,
      created_at: "2026-08-18T11:00:00Z",
    },
  ],
};

const page: OnboardingApplicationPage = {
  items: [application],
  total: 1,
  limit: 30,
  offset: 0,
  status_counts: {
    QUALIFICATION_REVIEW_REQUIRED: 1,
    PAYMENT_PENDING: 2,
  },
};

afterEach(() => vi.restoreAllMocks());

it("показывает воронку, карточку и выполняет действие через onboarding-бота", async () => {
  vi.spyOn(api, "adminApplications").mockResolvedValue(page);
  vi.spyOn(api, "adminApplication").mockResolvedValue(application);
  const execute = vi
    .spyOn(api, "executeAdminApplicationAction")
    .mockResolvedValue({
      message: "Кандидат допущен к созвону",
      delivered: true,
      application: {
        ...application,
        status: "BOOKING_LINK_SENT",
        available_actions: [
          "approve_after_call",
          "reject_after_call",
          "request_follow_up",
        ],
      },
    });

  renderPage(<AdminApplicationsPage />);

  expect(await screen.findByText("Иван Петров")).toBeInTheDocument();
  expect(screen.getByText("Найдено заявок: 1")).toBeInTheDocument();
  expect(
    screen.getByText("Ожидают оплату").closest(".application-kpi"),
  ).toHaveTextContent("2");

  await userEvent.click(screen.getByRole("button", { name: "Открыть" }));

  expect(
    await screen.findByText("Проходил курс по Python"),
  ).toBeInTheDocument();
  expect(screen.getByText("YouTube")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: "Допустить к созвону" }),
  );

  await waitFor(() =>
    expect(execute).toHaveBeenCalledWith(
      "app_123",
      "approve_qualification",
      null,
    ),
  );
});

it("показывает подробную анкету, полноту и загруженные документы", async () => {
  const detailedApplication: OnboardingApplicationDetail = {
    ...application,
    status: "APPLICATION_FORM_STARTED",
    form_answer_source: "redis_draft",
    form_state: "ApplicationFormStates:personal_data_consent",
    form_complete: true,
    form_missing_fields: [],
    form_answers: {
      direction: "Python",
      last_name: "Иванов",
      first_name: "Иван",
      patronymic: "Иванович",
      passport_series: "1234",
      passport_number: "567890",
      registration_address: "г. Москва, ул. Ленина, д. 1",
      phone: "+79999999999",
      email: "student@example.com",
      personal_data_consent: true,
    },
    form_documents: {
      passport_main_page_file: {
        uploaded: true,
        url: "https://files.example/passport.jpg",
        content_type: "image/jpeg",
        size: 2048,
      },
      passport_registration_page_file: {
        uploaded: false,
        url: null,
        content_type: null,
        size: null,
      },
    },
  };
  vi.spyOn(api, "adminApplications").mockResolvedValue({
    ...page,
    items: [detailedApplication],
  });
  vi.spyOn(api, "adminApplication").mockResolvedValue(detailedApplication);

  renderPage(<AdminApplicationsPage />);
  await userEvent.click(await screen.findByRole("button", { name: "Открыть" }));

  expect(await screen.findByText("Заполнена полностью")).toBeInTheDocument();
  expect(
    screen.getByText("Черновик из текущего диалога с ботом"),
  ).toBeInTheDocument();
  expect(
    screen.getByText("Текущий шаг: согласие на обработку данных"),
  ).toBeInTheDocument();
  expect(screen.getByText("567890")).toBeInTheDocument();
  expect(screen.getByText("г. Москва, ул. Ленина, д. 1")).toBeInTheDocument();
  expect(
    screen.getByRole("link", { name: "Открыть документ" }),
  ).toHaveAttribute("href", "https://files.example/passport.jpg");
});

it("возвращает заявку на предыдущий статус с подтверждением", async () => {
  vi.spyOn(api, "adminApplications").mockResolvedValue(page);
  vi.spyOn(api, "adminApplication").mockResolvedValue(application);
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const execute = vi
    .spyOn(api, "executeAdminApplicationAction")
    .mockResolvedValue({
      message: "Статус возвращён",
      delivered: null,
      application: {
        ...application,
        status: "QUALIFICATION_COMPLETED",
        rollback_status: "QUALIFICATION_STARTED",
      },
    });

  renderPage(<AdminApplicationsPage />);
  await userEvent.click(await screen.findByRole("button", { name: "Открыть" }));
  await userEvent.click(
    await screen.findByRole("button", {
      name: "Вернуть: Квалификация заполнена",
    }),
  );

  expect(window.confirm).toHaveBeenCalledWith(
    expect.stringContaining("уже отправленные сообщения"),
  );
  await waitFor(() =>
    expect(execute).toHaveBeenCalledWith("app_123", "rollback_status", null),
  );
});
