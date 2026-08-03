import { MantineProvider } from "@mantine/core";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";

import { PlatformProvider } from "../src/platform/PlatformProvider";

export function renderPage(
  element: ReactElement,
  path = "/",
  route = "/",
  child?: ReactElement,
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 0 },
      mutations: { retry: false },
    },
  });
  const router = createMemoryRouter(
    [
      {
        path: route,
        element,
        children: child ? [{ index: true, element: child }] : undefined,
      },
      {
        path: "*",
        element: <div />,
      },
    ],
    {
      initialEntries: [path],
    },
  );
  return render(
    <MantineProvider>
      <QueryClientProvider client={queryClient}>
        <PlatformProvider>
          <RouterProvider router={router} />
        </PlatformProvider>
      </QueryClientProvider>
    </MantineProvider>,
  );
}
