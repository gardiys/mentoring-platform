import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminCompanyAliasProposalsPage } from "../src/pages/AdminCompanyAliasProposalsPage";
import type { AdminCompanyAliasProposalRead } from "../src/types/api";
import { renderPage } from "./render";

const proposal: AdminCompanyAliasProposalRead = {
  id: "72000000-0000-4000-8000-000000000001",
  company_id: "72000000-0000-4000-8000-000000000002",
  company_name: "Wildberries",
  alias_name: "WB",
  suggested_by_user_id: "72000000-0000-4000-8000-000000000003",
  suggested_by_name: "Иван",
  suggested_by_telegram_username: "student_user",
  status: "pending",
  conflicting_company_id: null,
  conflicting_company_name: null,
  reviewed_by_name: null,
  reviewed_at: null,
  rejection_reason: null,
  created_at: "2026-08-12T10:00:00Z",
};

afterEach(() => vi.restoreAllMocks());

it("одобряет безопасное предложение алиаса из очереди", async () => {
  vi.spyOn(api, "adminCompanyAliasProposals").mockResolvedValue({
    items: [proposal],
    total: 1,
    limit: 20,
    offset: 0,
  });
  const moderate = vi
    .spyOn(api, "moderateCompanyAliasProposal")
    .mockReturnValue(new Promise(() => undefined));

  renderPage(<AdminCompanyAliasProposalsPage />);
  expect(await screen.findByText("«WB» → «Wildberries»")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Одобрить" }));

  expect(moderate).toHaveBeenCalledWith(proposal.id, {
    action: "approve",
    merge_conflicting_company: false,
    rejection_reason: null,
  });
});

it("требует отдельного подтверждения перед объединением компаний", async () => {
  const conflicting = {
    ...proposal,
    conflicting_company_id: "72000000-0000-4000-8000-000000000004",
    conflicting_company_name: "WB",
  };
  vi.spyOn(api, "adminCompanyAliasProposals").mockResolvedValue({
    items: [conflicting],
    total: 1,
    limit: 20,
    offset: 0,
  });
  vi.spyOn(window, "confirm").mockReturnValue(true);
  const moderate = vi
    .spyOn(api, "moderateCompanyAliasProposal")
    .mockReturnValue(new Promise(() => undefined));

  renderPage(<AdminCompanyAliasProposalsPage />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Объединить и одобрить" }),
  );

  expect(window.confirm).toHaveBeenCalled();
  expect(moderate).toHaveBeenCalledWith(proposal.id, {
    action: "approve",
    merge_conflicting_company: true,
    rejection_reason: null,
  });
});
