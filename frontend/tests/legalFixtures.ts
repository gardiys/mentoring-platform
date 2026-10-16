import { vi } from "vitest";
import * as client from "../src/api/client";

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
