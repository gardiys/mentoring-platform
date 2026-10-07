import type { MantineColorSchemeManager } from "@mantine/core";

// Keep in sync with the pre-paint script in index.html.
export const COLOR_SCHEME_STORAGE_KEY = "mentoring-platform-color-scheme-v2";

function isPlatformScheme(value: unknown): value is "light" | "dark" {
  return value === "light" || value === "dark";
}

export function createPlatformColorSchemeManager(): MantineColorSchemeManager {
  let listener: ((event: StorageEvent) => void) | undefined;
  return {
    get: () => {
      try {
        const stored = window.localStorage.getItem(COLOR_SCHEME_STORAGE_KEY);
        return isPlatformScheme(stored) ? stored : "dark";
      } catch {
        return "dark";
      }
    },
    set: (value) => {
      try {
        window.localStorage.setItem(
          COLOR_SCHEME_STORAGE_KEY,
          isPlatformScheme(value) ? value : "dark",
        );
      } catch {
        // Switching still works in this tab when browser storage is unavailable.
      }
    },
    subscribe: (onUpdate) => {
      listener = (event) => {
        try {
          if (
            event.storageArea === window.localStorage &&
            (event.key === COLOR_SCHEME_STORAGE_KEY || event.key === null)
          ) {
            onUpdate(
              isPlatformScheme(event.newValue) ? event.newValue : "dark",
            );
          }
        } catch {
          // Browser storage can be blocked independently of the UI.
        }
      };
      window.addEventListener("storage", listener);
    },
    unsubscribe: () => {
      if (listener) window.removeEventListener("storage", listener);
    },
    clear: () => {
      try {
        window.localStorage.removeItem(COLOR_SCHEME_STORAGE_KEY);
      } catch {
        // The provider resets its in-memory preference even without storage.
      }
    },
  };
}
