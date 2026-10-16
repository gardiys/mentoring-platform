import { fireEvent, screen, waitFor } from "@testing-library/react";
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
afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
});

it("восстанавливает незавершённую анкету после закрытия, сохраняя последний символ", async () => {
  const request = mockLegalCheckout({ email_verified: false });
  const form = (
    <LegalCheckout product="python_to_go_transition" applicationId="draft-1" />
  );
  const view = renderPage(form);
  const status = await screen.findByLabelText(/Текущий статус занятости/);
  await userEvent.type(status, "Р");
  await userEvent.type(
    screen.getByLabelText(/Текущая должность/),
    "Python developer",
  );
  await userEvent.click(
    screen.getByRole("textbox", { name: /Go уже является/ }),
  );
  await userEvent.click(await screen.findByRole("option", { name: "Да" }));
  await userEvent.type(
    screen.getByLabelText(/Пояснение/),
    "Использую Go в проекте",
  );
  await userEvent.click(screen.getAllByRole("checkbox")[0]!);
  await userEvent.type(screen.getByLabelText("Код из письма"), "12345678");
  fireEvent.change(screen.getByLabelText(/Текущая должность/), {
    target: { value: "Python developer!" },
  });
  view.unmount();
  renderPage(form);
  expect(await screen.findByLabelText(/Текущая должность/)).toHaveValue(
    "Python developer!",
  );
  expect(screen.getByLabelText(/Текущий статус занятости/)).toHaveValue("Р");
  expect(screen.getByRole("textbox", { name: /Go уже является/ })).toHaveValue(
    "Да",
  );
  expect(screen.getByLabelText(/Пояснение/)).toHaveValue(
    "Использую Go в проекте",
  );
  expect(screen.getByLabelText("Код из письма")).toHaveValue("");
  screen
    .getAllByRole("checkbox")
    .forEach((checkbox) => expect(checkbox).not.toBeChecked());
  expect(
    screen.getByRole("button", { name: /Перейти к оплате/ }),
  ).toBeDisabled();
  expect(request.mock.calls.every(([, options]) => !options?.method)).toBe(
    true,
  );
});

it("сохраняет очистку поля поверх серверного черновика и изолирует заявки", async () => {
  mockLegalCheckout().mockImplementation(
    async <T,>(path: string): Promise<T> => {
      if (path.endsWith("/questionnaire"))
        return {
          answers: {
            employment_status: "Работаю",
            position: "Старая должность",
          },
        } as T;
      return legalDetails as T;
    },
  );
  const form = (id: string) => (
    <LegalCheckout product="python_to_go_transition" applicationId={id} />
  );
  const first = renderPage(form("first"));
  const position = await screen.findByLabelText(/Текущая должность/);
  await userEvent.clear(position);
  first.unmount();
  const restored = renderPage(form("first"));
  expect(await screen.findByLabelText(/Текущая должность/)).toHaveValue("");
  expect(screen.getByLabelText(/Текущий статус занятости/)).toHaveValue(
    "Работаю",
  );
  restored.unmount();
  renderPage(form("second"));
  expect(await screen.findByLabelText(/Текущая должность/)).toHaveValue(
    "Старая должность",
  );
});

it("не роняет форму при повреждённом черновике и сообщает об ошибке сохранения", async () => {
  mockLegalCheckout();
  localStorage.setItem(
    "mentoring.questionnaire-draft.v1:python_to_go_transition:broken",
    "{",
  );
  vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
    throw new DOMException("Quota exceeded", "QuotaExceededError");
  });
  renderPage(
    <LegalCheckout product="python_to_go_transition" applicationId="broken" />,
  );
  const position = await screen.findByLabelText(/Текущая должность/);
  await userEvent.type(position, "Новая должность");
  expect(position).toHaveValue("Новая должность");
  expect(screen.getByText("Не удалось сохранить черновик")).toBeInTheDocument();
});

it("показывает ошибку загрузки серверной анкеты вместо пустой формы", async () => {
  const request = mockLegalCheckout();
  request.mockImplementation(async <T,>(path: string): Promise<T> => {
    if (path.endsWith("/questionnaire"))
      throw new Error("Не удалось загрузить анкету");
    return legalDetails as T;
  });
  renderPage(
    <LegalCheckout
      product="python_to_go_transition"
      applicationId="server-error"
    />,
  );
  expect(
    await screen.findByText("Не удалось загрузить данные"),
  ).toBeInTheDocument();
  expect(screen.queryByLabelText(/Текущая должность/)).not.toBeInTheDocument();
});

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
