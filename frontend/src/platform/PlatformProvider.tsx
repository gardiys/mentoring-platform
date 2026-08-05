import { type PropsWithChildren, useEffect, useMemo } from "react";

import { BrowserPlatformAdapter } from "./BrowserPlatformAdapter";
import type { PlatformAdapter } from "./PlatformAdapter";
import { PlatformContext } from "./platformContext";
import { TelegramPlatformAdapter } from "./TelegramPlatformAdapter";
import {
  isTelegramLaunchContext,
  TELEGRAM_SDK_READY_EVENT,
} from "./telegramSdk";

export function PlatformProvider({ children }: PropsWithChildren) {
  const adapter = useMemo<PlatformAdapter>(
    () =>
      isTelegramLaunchContext()
        ? new TelegramPlatformAdapter()
        : new BrowserPlatformAdapter(),
    [],
  );
  useEffect(() => {
    const initialize = () => {
      adapter.initialize();
    };
    initialize();
    window.addEventListener(TELEGRAM_SDK_READY_EVENT, initialize);
    return () => {
      window.removeEventListener(TELEGRAM_SDK_READY_EVENT, initialize);
    };
  }, [adapter]);
  return (
    <PlatformContext.Provider value={adapter}>
      {children}
    </PlatformContext.Provider>
  );
}
