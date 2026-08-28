interface TelegramBackButton {
  show?(): void;
  hide?(): void;
  onClick?(callback: () => void): void;
  offClick?(callback: () => void): void;
}

interface TelegramHapticFeedback {
  notificationOccurred?(type: "success"): void;
}

interface TelegramWebApp {
  initData?: string;
  platform?: string;
  version?: string;
  colorScheme?: "light" | "dark";
  BackButton?: TelegramBackButton;
  HapticFeedback?: TelegramHapticFeedback;
  ready?(): void;
  expand?(): void;
  onEvent?(event: "themeChanged", callback: () => void): void;
  offEvent?(event: "themeChanged", callback: () => void): void;
  close?(): void;
  openLink?(url: string, options?: { try_instant_view?: boolean }): void;
}

interface Window {
  Telegram?: { WebApp?: TelegramWebApp };
}
