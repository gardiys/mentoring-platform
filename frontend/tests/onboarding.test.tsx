import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { OnboardingPage } from "../src/pages/OnboardingPage";
import type { User } from "../src/types/api";
import { renderPage } from "./render";

const telegramUser: User = {
  id: "20000000-0000-4000-8000-000000000099",
  first_name: "Иван",
  last_name: null,
  email: null,
  telegram_id: 987654321,
  role: "student",
  onboarding_completed_at: null,
};

afterEach(() => vi.restoreAllMocks());

it("проводит ученика по шагам и завершает онбординг", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "me").mockResolvedValue(telegramUser);
  const complete = vi.spyOn(api, "completeOnboarding").mockResolvedValue({
    ...telegramUser,
    onboarding_completed_at: "2026-07-31T15:00:00Z",
  });

  renderPage(<OnboardingPage />);

  expect(
    await screen.findByText("Учитесь по понятному плану"),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Продолжить" }));
  expect(screen.getByText("Отмечайте реальный результат")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Продолжить" }));
  await user.click(screen.getByRole("button", { name: "Перейти к роадмапам" }));

  expect(complete).toHaveBeenCalledOnce();
});
