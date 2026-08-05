import "@mantine/core/styles.css";
import "@mantine/notifications/styles.css";
import "@fontsource/golos-text/400.css";
import "@fontsource/golos-text/500.css";
import "@fontsource/golos-text/600.css";
import "@fontsource/unbounded/600.css";
import "@fontsource/unbounded/700.css";
import "@fontsource/unbounded/800.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import "./styles.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { AppProviders } from "./app/providers";
import { loadTelegramSdk } from "./platform/telegramSdk";

async function bootstrap() {
  // A regular browser does not request Telegram SDK at all. A Mini App loads
  // the pinned same-origin copy before platform selection; the timeout keeps a
  // broken asset from leaving the root blank indefinitely.
  await loadTelegramSdk();
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <AppProviders>
        <App />
      </AppProviders>
    </StrictMode>,
  );
}

void bootstrap();
