import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClientProvider } from "@tanstack/react-query";
import { type PropsWithChildren, useState } from "react";

import { PlatformProvider } from "../platform/PlatformProvider";
import { createQueryClient } from "./queryClient";
import { brandCssVariables, brandTheme } from "./theme";
import { createPlatformColorSchemeManager } from "./colorScheme";
import { ThemeMetadata } from "./ThemeMetadata";

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(createQueryClient);
  const [colorSchemeManager] = useState(createPlatformColorSchemeManager);
  return (
    <MantineProvider
      colorSchemeManager={colorSchemeManager}
      defaultColorScheme="dark"
      theme={brandTheme}
      cssVariablesResolver={brandCssVariables}
    >
      <ThemeMetadata />
      <Notifications />
      <QueryClientProvider client={queryClient}>
        <PlatformProvider>{children}</PlatformProvider>
      </QueryClientProvider>
    </MantineProvider>
  );
}
