import { expect, it } from "vitest";

import { isLazyRouteImportError, lazyPage } from "../src/routes/lazyRoute";

it("распознаёт ошибки устаревших lazy chunks после деплоя", () => {
  expect(
    isLazyRouteImportError(
      new TypeError("Failed to fetch dynamically imported module"),
    ),
  ).toBe(true);
  expect(
    isLazyRouteImportError(new Error("ChunkLoadError: Loading chunk")),
  ).toBe(true);
  expect(isLazyRouteImportError(new Error("API request failed"))).toBe(false);
});

it("lazy route возвращает нужный компонент и не скрывает обычные ошибки", async () => {
  const TestPage = () => null;
  await expect(
    lazyPage(async () => ({ TestPage }), "TestPage")(),
  ).resolves.toEqual({ Component: TestPage });

  const error = new Error("Ошибка кода страницы");
  await expect(
    lazyPage<{ TestPage: () => null }>(async () => {
      throw error;
    }, "TestPage")(),
  ).rejects.toBe(error);
});
