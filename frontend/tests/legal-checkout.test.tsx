import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { LegalCheckout } from "../src/components/LegalCheckout";
import { mockLegalCheckout, legalDetails } from "./legalFixtures";
import { renderPage } from "./render";

vi.mock("../src/utils/openExternalResource", () => ({
  openExternalResource: async (promise: Promise<string>) => {
    await promise;
  },
}));
afterEach(() => vi.restoreAllMocks());

it("требует анкету и все три подтверждения и передаёт ожидаемую версию", async () => {
  const request = mockLegalCheckout();
  renderPage(
    <LegalCheckout
      product="python_to_go_transition"
      applicationId="application-1"
    />,
  );
  const pay = await screen.findByRole("button", { name: /Перейти к оплате/ });
  expect(pay).toBeDisabled();
  await userEvent.type(
    screen.getByLabelText(/Текущий статус занятости/),
    "Работаю",
  );
  await userEvent.type(
    screen.getByLabelText(/Текущая должность/),
    "Python developer",
  );
  await userEvent.type(screen.getByLabelText(/Формат работы/), "Удалённо");
  await userEvent.type(
    screen.getByLabelText(/Основные рабочие технологии/),
    "Python",
  );
  for (const field of screen
    .getAllByRole("textbox")
    .filter((element) => element.hasAttribute("aria-haspopup"))) {
    await userEvent.click(field);
    await userEvent.click(await screen.findByRole("option", { name: "Нет" }));
  }
  for (const checkbox of screen.getAllByRole("checkbox"))
    await userEvent.click(checkbox);
  expect(pay).toBeEnabled();
  await userEvent.click(pay);
  await waitFor(() =>
    expect(request).toHaveBeenCalledWith(
      expect.stringContaining("/go-transition/application-1/payment-link"),
      expect.objectContaining({ method: "POST" }),
    ),
  );
  const call = request.mock.calls.find(([path]) =>
    path.endsWith("/payment-link"),
  );
  const payload = JSON.parse(call?.[1]?.body as string);
  expect(payload.expected_offer_version_id).toBe(legalDetails.offer_version_id);
  expect(payload.confirmations).toEqual({
    offer: true,
    financial: true,
    truthful: true,
  });
  expect(payload.answers.go_in_current_work).toBe(false);
  expect(payload).not.toHaveProperty("amount");
});

it("требует подтверждение email и показывает адрес для документов", async () => {
  mockLegalCheckout({ email_verified: false });
  renderPage(
    <LegalCheckout
      product="repeat_python_mentorship"
      applicationId="application-1"
    />,
  );
  expect(
    await screen.findByText(/Подтвердите email перед оплатой/),
  ).toBeInTheDocument();
  expect(screen.getByText("student@example.com")).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /Перейти к оплате/ }),
  ).toBeDisabled();
  expect(screen.getByRole("link", { name: "Изменить email" })).toHaveAttribute(
    "href",
    "/payments",
  );
});

it("показывает обязательное пояснение при ответе да", async () => {
  mockLegalCheckout();
  renderPage(
    <LegalCheckout
      product="python_to_go_transition"
      applicationId="application-1"
    />,
  );
  await screen.findByText("Предварительные сведения");
  await userEvent.click(
    screen.getByRole("textbox", { name: /Go уже является/ }),
  );
  await userEvent.click(await screen.findByRole("option", { name: "Да" }));
  expect(screen.getByLabelText(/Пояснение/)).toBeRequired();
  expect(
    screen.getByRole("button", { name: /Перейти к оплате/ }),
  ).toBeDisabled();
});
