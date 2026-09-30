import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { api } from "../src/api/endpoints";
import { ReportDuplicateButton } from "../src/features/interviews/ReportDuplicateButton";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());
it("отправляет сообщение об открытой карточке одним нажатием и блокирует повторы", async () => {
  const report = vi
    .spyOn(api, "reportInterviewCardDuplicate")
    .mockResolvedValue({ id: "report", status: "pending" });
  const user = userEvent.setup();
  renderPage(<ReportDuplicateButton cardId="card-123" />);
  await user.click(screen.getByRole("button", { name: "Сообщить о дубле" }));
  await waitFor(() => expect(report).toHaveBeenCalledWith("card-123"));
  expect(
    await screen.findByRole("button", { name: "Сообщение отправлено" }),
  ).toBeDisabled();
});
