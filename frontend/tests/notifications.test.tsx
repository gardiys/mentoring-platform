import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { NotificationBell } from "../src/components/NotificationBell";
import { renderPage } from "./render";

afterEach(() => vi.restoreAllMocks());

it("показывает счётчик и помечает открытое уведомление прочитанным", async () => {
  vi.spyOn(api, "notifications").mockResolvedValue({
    items: [
      {
        id: "10000000-0000-4000-8000-000000000099",
        kind: "interview_published",
        title: "Новое собеседование в каталоге",
        body: "Техническое интервью в Example.",
        action_url: "/interviews/catalog/company-id?stage=stage-id",
        read_at: null,
        created_at: "2026-08-15T10:00:00Z",
      },
    ],
    total: 1,
    unread_count: 1,
    limit: 20,
    offset: 0,
  });
  const markRead = vi
    .spyOn(api, "markNotificationRead")
    .mockResolvedValue(undefined);

  renderPage(<NotificationBell />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /1 непрочитанных/ }));
  await user.click(
    await screen.findByRole("menuitem", {
      name: /Новое собеседование в каталоге/,
    }),
  );

  await waitFor(() => expect(markRead).toHaveBeenCalledOnce());
  expect(markRead.mock.calls[0]?.[0]).toBe(
    "10000000-0000-4000-8000-000000000099",
  );
});

it("позволяет прочитать все уведомления", async () => {
  vi.spyOn(api, "notifications").mockResolvedValue({
    items: [],
    total: 2,
    unread_count: 2,
    limit: 20,
    offset: 0,
  });
  const markAll = vi
    .spyOn(api, "markAllNotificationsRead")
    .mockResolvedValue(undefined);

  renderPage(<NotificationBell />);
  const user = userEvent.setup();
  await user.click(await screen.findByRole("button", { name: /2 непрочитанных/ }));
  await user.click(await screen.findByRole("button", { name: "Прочитать все" }));

  await waitFor(() => expect(markAll).toHaveBeenCalledOnce());
});

it("отменяет загрузку уведомлений при размонтировании", async () => {
  let requestSignal: AbortSignal | undefined;
  vi.spyOn(api, "notifications").mockImplementation(
    (_limit, _offset, signal) => {
      requestSignal = signal;
      return new Promise(() => undefined);
    },
  );

  const page = renderPage(<NotificationBell />);
  await waitFor(() => expect(requestSignal).toBeDefined());

  page.unmount();

  expect(requestSignal?.aborted).toBe(true);
});
