import { vi } from "vitest";
import * as client from "../src/api/client";
import type { components } from "../src/api/generated/schema";

export const adminGoQuestionnaire: components["schemas"]["AdminQuestionnaireRead"] =
  {
    application_id: "30000000-0000-4000-8000-000000000001",
    source: "payment",
    recorded_at: "2026-10-17T10:30:00Z",
    answers: {
      employment_status: "Работаю",
      position: "Python backend developer",
      work_format: "Удалённо",
      technologies: "Python, PostgreSQL, Go",
      existing_offers: true,
      existing_offers_details: "Оффер на Go-позицию на рассмотрении",
      selection_processes: false,
      previous_obligations: true,
      previous_obligations_details: "Остался один платёж по Python",
      go_in_current_work: false,
      previous_contract: "Договор Python от 2025 года",
    },
  };

export const legalDetails = {
  title: "Программа менторства",
  offer_version_id: "60000000-0000-4000-8000-000000000001",
  version_code: "2026-09-03",
  publication_date: "2026-09-03",
  pdf_url:
    "/api/v1/legal/offers/60000000-0000-4000-8000-000000000001/offer.pdf",
  financial_terms: {
    upfront_amount_minor: 3_000_000,
    success_fee_percent: 100,
    success_fee_installments: 2,
    success_fee_due_month_offsets: [1, 2],
  },
  checkboxes: {
    offer: "Я принимаю оферту программы",
    financial: "Я подтверждаю финансовые условия",
    truthful: "Я подтверждаю достоверность сведений",
  },
  email: "student@example.com",
  email_verified: true,
};

export function mockLegalCheckout(
  overrides: Partial<typeof legalDetails> = {},
) {
  return vi
    .spyOn(client, "apiRequest")
    .mockImplementation(async <T>(path: string): Promise<T> => {
      if (path.endsWith("/questionnaire")) return { answers: null } as T;
      if (path.includes("/applications/") || path.endsWith("/payment-link"))
        return { payment_url: "https://bank.example/pay" } as T;
      return { ...legalDetails, ...overrides } as T;
    });
}
