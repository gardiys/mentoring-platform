interface TelegramBackButton {
  show(): void;
  hide(): void;
  onClick(callback: () => void): void;
  offClick(callback: () => void): void;
}

interface TelegramHapticFeedback {
  notificationOccurred(type: "success"): void;
}

interface TelegramWebApp {
  initData: string;
  colorScheme: "light" | "dark";
  BackButton: TelegramBackButton;
  HapticFeedback?: TelegramHapticFeedback;
  ready(): void;
  expand(): void;
  onEvent(event: "themeChanged", callback: () => void): void;
  offEvent(event: "themeChanged", callback: () => void): void;
  close(): void;
}

interface Window {
  Telegram?: { WebApp?: TelegramWebApp };
}
