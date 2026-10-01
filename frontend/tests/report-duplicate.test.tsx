import { MantineProvider } from "@mantine/core";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../src/api/endpoints";
import { ReportDuplicateButton } from "../src/features/interviews/ReportDuplicateButton";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

function renderButton() {
  // jsdom has no geometry; Mantine's test environment disables detached-target hiding.
  renderPage(
    <MantineProvider env="test">
      <ReportDuplicateButton
        cardId="card-123"
        question="Зачем нужны индексы?"
      />
    </MantineProvider>,
  );
}

async function openConfirmation(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    screen.getByRole("button", {
      name: "Действия с вопросом: Зачем нужны индексы?",
    }),
  );
  await user.click(
    await screen.findByRole("menuitem", { name: "Сообщить о дубле" }),
  );
  const dialog = await screen.findByRole("dialog", {
    name: "Сообщить о дубликате?",
  });
  await waitFor(() => expect(dialog).toBeVisible());
  return dialog;
}

it("отправляет только после подтверждения и блокирует повторное сообщение", async () => {
  const report = vi
    .spyOn(api, "reportInterviewCardDuplicate")
    .mockResolvedValue({ id: "report", status: "pending" });
  const user = userEvent.setup();
  renderButton();
  expect(screen.queryByText("Сообщить о дубле")).not.toBeInTheDocument();
  const dialog = await openConfirmation(user);
  expect(within(dialog).getByText("Зачем нужны индексы?")).toBeVisible();
  expect(report).not.toHaveBeenCalled();
  await user.click(
    within(dialog).getByRole("button", { name: "Отправить сообщение" }),
  );
  await waitFor(() =>
    expect(report).toHaveBeenCalledExactlyOnceWith("card-123"),
  );
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  await user.click(
    screen.getByRole("button", { name: /Действия с вопросом:/ }),
  );
  expect(
    await screen.findByRole("menuitem", { name: "Сообщение отправлено" }),
  ).toBeDisabled();
});

it("отмена и Escape закрывают диалог без отправки", async () => {
  const report = vi.spyOn(api, "reportInterviewCardDuplicate");
  const user = userEvent.setup();
  renderButton();
  let dialog = await openConfirmation(user);
  await user.click(within(dialog).getByRole("button", { name: "Отмена" }));
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  dialog = await openConfirmation(user);
  expect(dialog).toBeVisible();
  await user.keyboard("{Escape}");
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(report).not.toHaveBeenCalled();
});

it("оставляет ошибку в диалоге и позволяет повторить отправку", async () => {
  const report = vi
    .spyOn(api, "reportInterviewCardDuplicate")
    .mockRejectedValueOnce(new Error("Не удалось отправить сообщение"))
    .mockResolvedValueOnce({ id: "report", status: "pending" });
  const user = userEvent.setup();
  renderButton();
  const dialog = await openConfirmation(user);
  await user.click(
    within(dialog).getByRole("button", { name: "Отправить сообщение" }),
  );
  expect(await within(dialog).findByRole("alert")).toHaveTextContent(
    "Не удалось отправить сообщение",
  );
  await user.click(
    within(dialog).getByRole("button", { name: "Отправить сообщение" }),
  );
  await waitFor(() =>
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
  );
  expect(report).toHaveBeenCalledTimes(2);
});

it("блокирует повторный клик и закрытие во время отправки", async () => {
  const report = vi
    .spyOn(api, "reportInterviewCardDuplicate")
    .mockReturnValue(new Promise(() => {}));
  const user = userEvent.setup();
  renderButton();
  const dialog = await openConfirmation(user);
  const submit = within(dialog).getByRole("button", {
    name: "Отправить сообщение",
  });
  await user.dblClick(submit);
  expect(report).toHaveBeenCalledTimes(1);
  expect(submit).toBeDisabled();
  expect(within(dialog).getByRole("button", { name: "Отмена" })).toBeDisabled();
  await user.keyboard("{Escape}");
  expect(dialog).toBeVisible();
});
