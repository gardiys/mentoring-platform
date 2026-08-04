import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import { api } from "../src/api/endpoints";
import { AdminUsefulLinksPage } from "../src/pages/AdminUsefulLinksPage";
import type { PinnedResourceLinkRead } from "../src/types/api";
import { renderPage } from "./render";

function usefulLink(
  overrides: Partial<PinnedResourceLinkRead> = {},
): PinnedResourceLinkRead {
  return {
    id: "60000000-0000-4000-8000-000000000001",
    title: "Python documentation",
    description: "Официальная документация языка",
    url: "https://docs.python.org/3/",
    position: 10,
    created_at: "2026-08-04T10:00:00Z",
    updated_at: "2026-08-04T10:00:00Z",
    ...overrides,
  };
}

afterEach(() => vi.restoreAllMocks());

it("показывает полезные ссылки и открывает их в новой вкладке", async () => {
  vi.spyOn(api, "adminUsefulLinks").mockResolvedValue([usefulLink()]);

  renderPage(
    <AdminUsefulLinksPage />,
    "/admin/useful-links",
    "/admin/useful-links",
  );

  expect(await screen.findByText("Python documentation")).toBeInTheDocument();
  expect(
    screen.getByText("Официальная документация языка"),
  ).toBeInTheDocument();
  expect(screen.getByText("10")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Открыть ссылку" })).toHaveAttribute(
    "href",
    "https://docs.python.org/3/",
  );
  expect(screen.getByRole("link", { name: "Открыть ссылку" })).toHaveAttribute(
    "target",
    "_blank",
  );
});

it("создаёт полезную ссылку", async () => {
  vi.spyOn(api, "adminUsefulLinks").mockResolvedValue([]);
  const create = vi
    .spyOn(api, "createAdminUsefulLink")
    .mockReturnValue(new Promise(() => undefined));

  renderPage(
    <AdminUsefulLinksPage />,
    "/admin/useful-links",
    "/admin/useful-links",
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "+ Добавить ссылку" }),
  );
  const dialog = await screen.findByRole("dialog");
  await userEvent.type(
    within(dialog).getByLabelText(/^Название/),
    "Go playground",
  );
  await userEvent.type(
    within(dialog).getByLabelText("Описание"),
    "Песочница для экспериментов",
  );
  await userEvent.type(
    within(dialog).getByLabelText(/^URL/),
    "https://go.dev/play/",
  );
  const position = within(dialog).getByLabelText(/^Позиция/);
  await userEvent.clear(position);
  await userEvent.type(position, "5");
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Добавить ссылку" }),
  );

  await waitFor(() =>
    expect(create).toHaveBeenCalledWith({
      title: "Go playground",
      description: "Песочница для экспериментов",
      url: "https://go.dev/play/",
      position: 5,
    }),
  );
});

it("редактирует полезную ссылку", async () => {
  const link = usefulLink();
  vi.spyOn(api, "adminUsefulLinks").mockResolvedValue([link]);
  const update = vi
    .spyOn(api, "updateAdminUsefulLink")
    .mockReturnValue(new Promise(() => undefined));

  renderPage(
    <AdminUsefulLinksPage />,
    "/admin/useful-links",
    "/admin/useful-links",
  );

  await userEvent.click(
    await screen.findByRole("button", { name: "Изменить" }),
  );
  const dialog = await screen.findByRole("dialog");
  const title = within(dialog).getByLabelText(/^Название/);
  await userEvent.clear(title);
  await userEvent.type(title, "Python docs");
  const description = within(dialog).getByLabelText("Описание");
  await userEvent.clear(description);
  const url = within(dialog).getByLabelText(/^URL/);
  await userEvent.clear(url);
  await userEvent.type(url, "https://docs.python.org/");
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Сохранить" }),
  );

  await waitFor(() =>
    expect(update).toHaveBeenCalledWith(link.id, {
      title: "Python docs",
      description: null,
      url: "https://docs.python.org/",
      position: 10,
    }),
  );
});

it("удаляет полезную ссылку только после подтверждения", async () => {
  const link = usefulLink();
  vi.spyOn(api, "adminUsefulLinks").mockResolvedValue([link]);
  const remove = vi
    .spyOn(api, "deleteAdminUsefulLink")
    .mockReturnValue(new Promise(() => undefined));
  vi.spyOn(window, "confirm")
    .mockReturnValueOnce(false)
    .mockReturnValueOnce(true);

  renderPage(
    <AdminUsefulLinksPage />,
    "/admin/useful-links",
    "/admin/useful-links",
  );

  const deleteButton = await screen.findByRole("button", { name: "Удалить" });
  await userEvent.click(deleteButton);
  expect(remove).not.toHaveBeenCalled();

  await userEvent.click(deleteButton);
  expect(remove).toHaveBeenCalledOnce();
  expect(remove.mock.calls[0]?.[0]).toBe(link.id);
});
