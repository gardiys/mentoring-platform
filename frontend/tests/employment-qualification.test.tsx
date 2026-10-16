import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import {
  EmploymentQualificationStaffPanel,
  EmploymentQualificationStudentPanel,
} from "../src/components/EmploymentQualificationPanel";
import type { EmploymentCase } from "../src/types/api";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

it("связывает решение о новой Go-работе с принятой офертой без ручной настройки политики", async () => {
  const go = {
    ...employmentCase,
    direction: "go" as const,
    contract_id: "go-contract",
    contract_number: "GO-42",
    policy_version: "GO-42",
    policy_is_legacy: false,
  };
  vi.spyOn(api, "employmentCasesForStudent").mockResolvedValue({
    items: [go],
    total: 1,
  });
  const assess = vi.spyOn(api, "assessEmploymentCase").mockResolvedValue(go);
  renderPage(<EmploymentQualificationStaffPanel studentId={go.student_id} />);
  await userEvent.click(
    await screen.findByText("Квалифицировать фактическую работу"),
  );
  await userEvent.click(
    await screen.findByRole("textbox", { name: "Решение" }),
  );
  await userEvent.click(screen.getByRole("option", { name: "Профильная" }));
  await userEvent.type(
    screen.getByLabelText(/^Дата начала профильной деятельности/),
    "2027-01-31",
  );
  await userEvent.click(
    screen.getByRole("textbox", {
      name: /^Критерий существенного использования/,
    }),
  );
  await userEvent.click(
    screen.getByRole("option", { name: "Регулярная разработка" }),
  );
  await userEvent.type(
    screen.getByLabelText(/^Мотивированное решение/),
    "Подтверждена новая работа на Go по условиям оферты",
  );
  await userEvent.click(
    screen.getByRole("checkbox", { name: /Подтверждаю.*GO-42/ }),
  );
  await userEvent.click(
    screen.getByRole("button", { name: "Подтвердить решение" }),
  );
  await waitFor(() =>
    expect(assess).toHaveBeenCalledWith(
      go.student_id,
      go.id,
      expect.objectContaining({ contract_billing_confirmed: true }),
    ),
  );
  expect(
    screen.queryByText(/не связан с принятой версией договорной политики/),
  ).not.toBeInTheDocument();
});

const employmentCase: EmploymentCase = {
  id: "10000000-0000-4000-8000-000000000010",
  student_id: "10000000-0000-4000-8000-000000000011",
  track_id: "10000000-0000-4000-8000-000000000012",
  direction: "python",
  company_name: "Пример",
  vacancy_title: "PHP Developer",
  official_job_title: "PHP Developer",
  activity_type: "employment_contract",
  offer_received_at: "2026-09-01",
  offer_accepted_at: null,
  contract_signed_at: null,
  expected_start_date: "2026-09-10",
  employment_started_at: null,
  employment_ended_at: null,
  vacancy_stack: ["PHP", "Python"],
  offer_stack: ["PHP"],
  actual_stack: [],
  actual_duties: null,
  project_description: null,
  team_description: null,
  differences_description: null,
  net_salary_kopecks: 20_000_000,
  case_status: "awaiting_actual_duties",
  employment_status: "active",
  profile_activity_started_at: null,
  profile_activity_ended_at: null,
  billing_on_hold: false,
  lock_version: 1,
  policy_version: "repeat-python:v1",
  policy_is_legacy: false,
  policy_control_period_started_at: "2026-01-01",
  policy_control_period_ended_at: "2026-12-31",
  policy_extension_ended_at: null,
  events: [],
  technology_usages: [],
  assessments: [],
  qualification_window: null,
  evidence: [],
  followups: [],
  disputes: [],
  billing_status: null,
  ai_suggestions: [],
  expected_information: [
    "employment_started_at",
    "actual_duties",
    "actual_stack",
  ],
  created_at: "2026-09-01T10:00:00Z",
  updated_at: "2026-09-01T10:00:00Z",
};

it("фиксирует принятие оффера отдельным событием", async () => {
  vi.spyOn(api, "myEmploymentCases").mockResolvedValue({
    items: [employmentCase],
    total: 1,
  });
  const report = vi
    .spyOn(api, "reportEmploymentOfferStatus")
    .mockResolvedValue({ ...employmentCase, offer_accepted_at: "2026-09-03" });

  renderPage(<EmploymentQualificationStudentPanel />);
  await userEvent.click(await screen.findByText("Принятие оффера и договор"));
  await userEvent.type(screen.getByLabelText("Фактическая дата"), "2026-09-03");
  await userEvent.click(
    screen.getByRole("button", { name: "Сохранить событие" }),
  );

  await waitFor(() =>
    expect(report).toHaveBeenCalledWith(
      employmentCase.id,
      expect.objectContaining({
        event: "offer_accepted",
        effective_at: "2026-09-03",
        expected_lock_version: 1,
      }),
    ),
  );
});

it("показывает сотруднику предупреждение перед профильным решением", async () => {
  vi.spyOn(api, "employmentCasesForStudent").mockResolvedValue({
    items: [
      {
        ...employmentCase,
        employment_started_at: "2026-09-10",
        actual_duties: "Регулярно разрабатывает внутренний сервис на Python.",
        actual_stack: ["PHP", "Python"],
        case_status: "awaiting_staff_review",
      },
    ],
    total: 1,
  });

  renderPage(
    <EmploymentQualificationStaffPanel studentId={employmentCase.student_id} />,
  );
  await userEvent.click(
    await screen.findByText("Квалифицировать фактическую работу"),
  );

  expect(
    screen.getByText(/Решение может создать или пересчитать/),
  ).toBeInTheDocument();
});
