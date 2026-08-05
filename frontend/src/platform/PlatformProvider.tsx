import { useMantineColorScheme } from "@mantine/core";
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
  const { setColorScheme } = useMantineColorScheme();
  const adapter = useMemo<PlatformAdapter>(
    () =>
      isTelegramLaunchContext()
        ? new TelegramPlatformAdapter()
        : new BrowserPlatformAdapter(),
    [],
  );
  useEffect(() => {
    let unsubscribeTheme: () => void = () => undefined;
    const initialize = () => {
      unsubscribeTheme();
      adapter.initialize();
      const scheme = adapter.getColorScheme();
      if (scheme) setColorScheme(scheme);
      unsubscribeTheme = adapter.onThemeChange(setColorScheme);
    };
    initialize();
    window.addEventListener(TELEGRAM_SDK_READY_EVENT, initialize);
    return () => {
      window.removeEventListener(TELEGRAM_SDK_READY_EVENT, initialize);
      unsubscribeTheme();
    };
  }, [adapter, setColorScheme]);
  return (
    <PlatformContext.Provider value={adapter}>
      {children}
    </PlatformContext.Provider>
  );
}
