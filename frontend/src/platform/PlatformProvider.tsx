import { useMantineColorScheme } from "@mantine/core";
import { type PropsWithChildren, useEffect, useMemo } from "react";

import { BrowserPlatformAdapter } from "./BrowserPlatformAdapter";
import type { PlatformAdapter } from "./PlatformAdapter";
import { PlatformContext } from "./platformContext";
import { TelegramPlatformAdapter } from "./TelegramPlatformAdapter";

export function PlatformProvider({ children }: PropsWithChildren) {
  const { setColorScheme } = useMantineColorScheme();
  const adapter = useMemo<PlatformAdapter>(
    () =>
      window.Telegram?.WebApp?.initData
        ? new TelegramPlatformAdapter()
        : new BrowserPlatformAdapter(),
    [],
  );
  useEffect(() => {
    adapter.initialize();
    const scheme = adapter.getColorScheme();
    if (scheme) setColorScheme(scheme);
    return adapter.onThemeChange(setColorScheme);
  }, [adapter, setColorScheme]);
  return (
    <PlatformContext.Provider value={adapter}>
      {children}
    </PlatformContext.Provider>
  );
}
