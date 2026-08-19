import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminCardAutomationDuplicatesPage } from "../src/pages/AdminCardAutomationDuplicatesPage";
import type { InterviewCardDuplicateCandidate } from "../src/types/api";
import { renderPage } from "./render";

const leftId = "60000000-0000-4000-8000-000000000001";
const rightId = "60000000-0000-4000-8000-000000000002";

const candidate: InterviewCardDuplicateCandidate = {
  pair_key: `${leftId}:${rightId}`,
  similarity: 0.84,
  matched_source: "card",
  matched_text: "Какие индексы вы знаете?",
  left: {
    id: leftId,
    deck_id: "61000000-0000-4000-8000-000000000001",
    deck_title: "Python questions",
    direction_id: "30000000-0000-4000-8000-000000000001",
    direction_slug: "python",
    direction_title: "Python",
    category: "Базы данных",
    subcategory: "Индексы",
    question_markdown: "Какие индексы вы знаете?",
    answer_markdown: "B-tree, hash и специализированные индексы.",
    companies: "Acme",
    asked_count: 5,
    frequency: "frequent",
    updated_at: "2026-08-17T10:00:00Z",
  },
  right: {
    id: rightId,
    deck_id: "61000000-0000-4000-8000-000000000001",
    deck_title: "Python questions",
    direction_id: "30000000-0000-4000-8000-000000000001",
    direction_slug: "python",
    direction_title: "Python",
    category: "SQL",
    subcategory: null,
    question_markdown: "Зачем нужны индексы и когда их использовать?",
    answer_markdown: "Индексы ускоряют чтение ценой записи и памяти.",
    companies: "Beta",
    asked_count: 2,
    frequency: "occasional",
    updated_at: "2026-08-17T11:00:00Z",
  },
};

afterEach(() => vi.restoreAllMocks());

it("сравнивает ответы и объединяет карточки только после явного подтверждения", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "adminTracks").mockResolvedValue([
    {
      id: candidate.left.direction_id,
      slug: "python",
      title: "Python",
      description: null,
      position: 0,
      is_published: true,
      roadmaps: [],
      student_ids: [],
    },
  ]);
  vi.spyOn(api, "adminInterviewCardDuplicates").mockResolvedValue({
    items: [candidate],
    total: 1,
    limit: 20,
    offset: 0,
    cache_status: "ready",
    cache_generated_at: "2026-08-19T09:00:00Z",
    cache_refreshing: false,
  });
  const merge = vi
    .spyOn(api, "mergeAdminInterviewCardDuplicate")
    .mockResolvedValue({
      review_id: "62000000-0000-4000-8000-000000000001",
      decision: "merged",
      primary_card_id: rightId,
      archived_card_id: leftId,
      moved_occurrences: 3,
      deduplicated_occurrences: 1,
      merged_progress_records: 2,
    });

  renderPage(
    <AdminCardAutomationDuplicatesPage />,
    "/admin/card-automation/duplicates",
    "/admin/card-automation/duplicates",
  );

  await user.click(await screen.findByText(candidate.left.question_markdown));
  const dialog = await screen.findByRole("dialog");
  expect(
    within(dialog).getByText(candidate.left.answer_markdown),
  ).toBeInTheDocument();
  expect(
    within(dialog).getByText(candidate.right.answer_markdown),
  ).toBeInTheDocument();

  await user.click(within(dialog).getByText(candidate.right.question_markdown));
  await user.type(
    within(dialog).getByPlaceholderText(
      "Например: вопросы проверяют одинаковое понимание индексов",
    ),
    "Одинаковый объём знаний",
  );
  await user.click(
    within(dialog).getByLabelText(
      "Я проверил оба ответа и подтверждаю объединение",
    ),
  );
  await user.click(
    within(dialog).getByRole("button", { name: "Объединить карточки" }),
  );

  await waitFor(() => expect(merge).toHaveBeenCalledTimes(1));
  expect(merge.mock.calls[0]?.[0]).toEqual({
    left_card_id: leftId,
    right_card_id: rightId,
    primary_card_id: rightId,
    expected_left_updated_at: candidate.left.updated_at,
    expected_right_updated_at: candidate.right.updated_at,
    reason: "Одинаковый объём знаний",
  });
  expect(merge.mock.calls[0]?.[1]).toEqual(expect.any(String));
});

it("запускает пересчёт в фоне и продолжает показывать кешированный список", async () => {
  const user = userEvent.setup();
  vi.spyOn(api, "adminTracks").mockResolvedValue([]);
  vi.spyOn(api, "adminInterviewCardDuplicates").mockResolvedValue({
    items: [candidate],
    total: 1,
    limit: 20,
    offset: 0,
    cache_status: "ready",
    cache_generated_at: "2026-08-19T09:00:00Z",
    cache_refreshing: false,
  });
  const refresh = vi
    .spyOn(api, "refreshAdminInterviewCardDuplicates")
    .mockResolvedValue({ status: "queued" });

  renderPage(
    <AdminCardAutomationDuplicatesPage />,
    "/admin/card-automation/duplicates",
    "/admin/card-automation/duplicates",
  );

  expect(
    await screen.findByText(candidate.left.question_markdown),
  ).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Пересчитать в фоне" }));

  await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
  expect(
    screen.getByText(candidate.left.question_markdown),
  ).toBeInTheDocument();
});
