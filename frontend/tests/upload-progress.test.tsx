import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";

import { UploadProgressPanel } from "../src/components/UploadProgressPanel";
import { renderPage } from "./render";

it("показывает скорость, ETA и позволяет отменить передачу файла", async () => {
  const onCancel = vi.fn();
  renderPage(
    <UploadProgressPanel
      status={{
        phase: "uploading",
        percent: 50,
        uploadedBytes: 50 * 1024 * 1024,
        totalBytes: 100 * 1024 * 1024,
        bytesPerSecond: 2 * 1024 * 1024,
        etaSeconds: 25,
      }}
      onCancel={onCancel}
    />,
  );

  expect(screen.getByText("Загружаем файл… 50%")).toBeInTheDocument();
  expect(
    screen.getByText("2.0 МБ/с · осталось около 25 сек."),
  ).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Отменить" }));
  expect(onCancel).toHaveBeenCalledOnce();
});

it("позволяет отменить подготовку upload-сессии", async () => {
  const onCancel = vi.fn();
  renderPage(
    <UploadProgressPanel
      status={{
        phase: "preparing",
        percent: 0,
        uploadedBytes: 0,
        totalBytes: 100,
        bytesPerSecond: null,
        etaSeconds: null,
      }}
      onCancel={onCancel}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Отменить" }));
  expect(onCancel).toHaveBeenCalledOnce();
});

it("после передачи файла показывает отдельную фазу финализации", () => {
  renderPage(
    <UploadProgressPanel
      status={{
        phase: "finalizing",
        percent: 100,
        uploadedBytes: 100,
        totalBytes: 100,
        bytesPerSecond: null,
        etaSeconds: null,
      }}
      onCancel={vi.fn()}
    />,
  );

  expect(screen.getByText("Проверяем и сохраняем…")).toBeInTheDocument();
  expect(
    screen.getByText(/Файл уже загружен. Не закрывайте страницу/),
  ).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Отменить" }),
  ).not.toBeInTheDocument();
});
