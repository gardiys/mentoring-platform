import {
  localStorageColorSchemeManager,
  MantineProvider,
} from "@mantine/core";
import { Notifications } from "@mantine/notifications";
import { QueryClientProvider } from "@tanstack/react-query";
import { type PropsWithChildren, useState } from "react";

import { PlatformProvider } from "../platform/PlatformProvider";
import { createQueryClient } from "./queryClient";
import { brandTheme } from "./theme";

const colorSchemeManager = localStorageColorSchemeManager({
  key: "mentoring-platform-color-scheme-v2",
});

export function AppProviders({ children }: PropsWithChildren) {
  const [queryClient] = useState(createQueryClient);
  return (
    <MantineProvider
      colorSchemeManager={colorSchemeManager}
      defaultColorScheme="dark"
      theme={brandTheme}
    >
      <Notifications />
      <QueryClientProvider client={queryClient}>
        <PlatformProvider>{children}</PlatformProvider>
      </QueryClientProvider>
    </MantineProvider>
  );
}
