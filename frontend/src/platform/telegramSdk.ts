const TELEGRAM_SDK_PATH = "/vendor/telegram-web-app-2026-07-14.js";
const TELEGRAM_SDK_SCRIPT_ATTRIBUTE = "telegramSdk";
const TELEGRAM_SDK_SCRIPT_SELECTOR = "script[data-telegram-sdk]";
const TELEGRAM_INIT_PARAMS_STORAGE_KEY = "__telegram__initParams";
const DEFAULT_TELEGRAM_SDK_TIMEOUT_MS = 3_000;

export const TELEGRAM_SDK_READY_EVENT = "mentoring:telegram-sdk-ready";

export type TelegramSdkLoadResult =
  "not-needed" | "already-ready" | "loaded" | "failed" | "timeout";

type TelegramLaunchParams = {
  tgWebAppData?: unknown;
  tgWebAppPlatform?: unknown;
  tgWebAppVersion?: unknown;
};

type TelegramBridgeWindow = Window & {
  TelegramWebviewProxy?: unknown;
  webkit?: {
    messageHandlers?: {
      TelegramWebviewProxy?: unknown;
    };
  };
};

let sdkLoadPromise: Promise<TelegramSdkLoadResult> | null = null;

function parseUrlLaunchParams(windowValue: Window): TelegramLaunchParams {
  const sources: URLSearchParams[] = [];
  const rawHash = windowValue.location.hash.replace(/^#/, "");
  if (rawHash) {
    const queryIndex = rawHash.indexOf("?");
    sources.push(
      new URLSearchParams(
        queryIndex >= 0 ? rawHash.slice(queryIndex + 1) : rawHash,
      ),
    );
  }
  if (windowValue.location.search) {
    sources.push(new URLSearchParams(windowValue.location.search));
  }

  for (const source of sources) {
    const data = source.get("tgWebAppData");
    const platform = source.get("tgWebAppPlatform");
    const version = source.get("tgWebAppVersion");
    if (data !== null || platform !== null || version !== null) {
      return {
        tgWebAppData: data,
        tgWebAppPlatform: platform,
        tgWebAppVersion: version,
      };
    }
  }
  return {};
}

function parseStoredLaunchParams(windowValue: Window): TelegramLaunchParams {
  try {
    const raw = windowValue.sessionStorage.getItem(
      TELEGRAM_INIT_PARAMS_STORAGE_KEY,
    );
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    return typeof parsed === "object" && parsed !== null
      ? (parsed as TelegramLaunchParams)
      : {};
  } catch {
    return {};
  }
}

function launchParams(windowValue: Window): TelegramLaunchParams {
  const fromUrl = parseUrlLaunchParams(windowValue);
  const fromStorage = parseStoredLaunchParams(windowValue);
  return {
    tgWebAppData: fromUrl.tgWebAppData ?? fromStorage.tgWebAppData,
    tgWebAppPlatform: fromUrl.tgWebAppPlatform ?? fromStorage.tgWebAppPlatform,
    tgWebAppVersion: fromUrl.tgWebAppVersion ?? fromStorage.tgWebAppVersion,
  };
}

export function getTelegramInitData(
  windowValue: Window = window,
): string | null {
  const sdkInitData = windowValue.Telegram?.WebApp?.initData;
  if (typeof sdkInitData === "string" && sdkInitData.length > 0) {
    return sdkInitData;
  }
  const rawInitData = launchParams(windowValue).tgWebAppData;
  return typeof rawInitData === "string" && rawInitData.length > 0
    ? rawInitData
    : null;
}

export function isTelegramLaunchContext(windowValue: Window = window): boolean {
  if (getTelegramInitData(windowValue)) return true;

  const sdkPlatform = windowValue.Telegram?.WebApp?.platform;
  if (
    typeof sdkPlatform === "string" &&
    sdkPlatform.length > 0 &&
    sdkPlatform !== "unknown"
  ) {
    return true;
  }

  const params = launchParams(windowValue);
  if (
    typeof params.tgWebAppPlatform === "string" ||
    typeof params.tgWebAppVersion === "string"
  ) {
    return true;
  }

  const bridgeWindow = windowValue as TelegramBridgeWindow;
  return Boolean(
    bridgeWindow.TelegramWebviewProxy ||
    bridgeWindow.webkit?.messageHandlers?.TelegramWebviewProxy,
  );
}

export function loadTelegramSdk(
  windowValue: Window = window,
  documentValue: Document = document,
  timeoutMs = DEFAULT_TELEGRAM_SDK_TIMEOUT_MS,
): Promise<TelegramSdkLoadResult> {
  if (!isTelegramLaunchContext(windowValue)) {
    return Promise.resolve("not-needed");
  }
  if (windowValue.Telegram?.WebApp) {
    return Promise.resolve("already-ready");
  }
  if (sdkLoadPromise) return sdkLoadPromise;

  sdkLoadPromise = new Promise((resolve) => {
    let settled = false;
    const finish = (result: TelegramSdkLoadResult) => {
      if (settled) return;
      settled = true;
      windowValue.clearTimeout(timeoutId);
      resolve(result);
    };

    const existing = documentValue.querySelector<HTMLScriptElement>(
      TELEGRAM_SDK_SCRIPT_SELECTOR,
    );
    const script = existing ?? documentValue.createElement("script");
    script.addEventListener(
      "load",
      () => {
        windowValue.dispatchEvent(new Event(TELEGRAM_SDK_READY_EVENT));
        finish(windowValue.Telegram?.WebApp ? "loaded" : "failed");
      },
      { once: true },
    );
    script.addEventListener("error", () => finish("failed"), { once: true });

    const timeoutId = windowValue.setTimeout(
      () => finish("timeout"),
      Math.max(1, timeoutMs),
    );
    if (!existing) {
      script.src = TELEGRAM_SDK_PATH;
      script.async = true;
      script.dataset[TELEGRAM_SDK_SCRIPT_ATTRIBUTE] = "true";
      documentValue.head.appendChild(script);
    }
  });
  return sdkLoadPromise;
}

export function resetTelegramSdkLoaderForTests(): void {
  sdkLoadPromise = null;
}
