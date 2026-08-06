import type { ComponentType } from "react";

const CHUNK_RELOAD_PREFIX = "mentoring.lazy-route-reload:";
const CHUNK_RELOAD_COOLDOWN_MS = 30_000;
const CHUNK_ERROR_PATTERN =
  /chunkloaderror|loading chunk|failed to fetch dynamically imported module|error loading dynamically imported module|importing a module script failed|load failed/i;

export function isLazyRouteImportError(error: unknown) {
  return error instanceof Error && CHUNK_ERROR_PATTERN.test(error.message);
}

function reloadKey() {
  return `${CHUNK_RELOAD_PREFIX}${window.location.pathname}${window.location.search}`;
}

function reloadOnceAfterDeploy(error: unknown) {
  if (!isLazyRouteImportError(error)) return false;

  try {
    const key = reloadKey();
    const previousAttempt = Number(window.sessionStorage.getItem(key));
    const now = Date.now();
    if (
      Number.isFinite(previousAttempt) &&
      previousAttempt > 0 &&
      now - previousAttempt < CHUNK_RELOAD_COOLDOWN_MS
    ) {
      return false;
    }
    window.sessionStorage.setItem(key, String(now));
    window.location.reload();
    return true;
  } catch {
    return false;
  }
}

export function lazyPage<TModule>(
  loader: () => Promise<TModule>,
  exportName: keyof TModule,
) {
  return async () => {
    try {
      const module = await loader();
      try {
        window.sessionStorage.removeItem(reloadKey());
      } catch {
        // Private browsing may make sessionStorage unavailable.
      }
      return { Component: module[exportName] as ComponentType };
    } catch (error) {
      if (reloadOnceAfterDeploy(error)) {
        // Keep the current navigation pending while the browser reloads with
        // the new index.html and its current asset hashes.
        return await new Promise<never>(() => undefined);
      }
      throw error;
    }
  };
}
