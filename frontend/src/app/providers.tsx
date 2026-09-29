import { MantineProvider } from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClientProvider } from "@tanstack/react-query";
import { type PropsWithChildren, useState } from "react";

import { PlatformProvider } from "../platform/PlatformProvider";
import { createQueryClient } from "./queryClient";
import { brandCssVariables, brandTheme } from "./theme";

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(createQueryClient);
  return (
    <MantineProvider
      forceColorScheme="dark"
      defaultColorScheme="dark"
      theme={brandTheme}
      cssVariablesResolver={brandCssVariables}
    >
      <Notifications />
      <QueryClientProvider client={queryClient}>
        <PlatformProvider>{children}</PlatformProvider>
      </QueryClientProvider>
    </MantineProvider>
  );
}
