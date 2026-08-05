import type { PlatformAdapter } from "./PlatformAdapter";
import { getTelegramInitData } from "./telegramSdk";

export class TelegramPlatformAdapter implements PlatformAdapter {
  readonly platform = "telegram" as const;
  readonly isTelegram = true;

  getTelegramInitData(): string | null {
    return getTelegramInitData();
  }

  initialize(): void {
    window.Telegram?.WebApp?.ready?.();
    window.Telegram?.WebApp?.expand?.();
  }

  getColorScheme(): "light" | "dark" | null {
    return window.Telegram?.WebApp?.colorScheme ?? null;
  }

  onThemeChange(callback: (scheme: "light" | "dark") => void): () => void {
    const handler = () => {
      const scheme = this.getColorScheme();
      if (scheme) callback(scheme);
    };
    window.Telegram?.WebApp?.onEvent?.("themeChanged", handler);
    return () => window.Telegram?.WebApp?.offEvent?.("themeChanged", handler);
  }

  onBackButton(callback: () => void): () => void {
    window.Telegram?.WebApp?.BackButton?.onClick?.(callback);
    return () => window.Telegram?.WebApp?.BackButton?.offClick?.(callback);
  }

  showBackButton(): void {
    window.Telegram?.WebApp?.BackButton?.show?.();
  }

  hideBackButton(): void {
    window.Telegram?.WebApp?.BackButton?.hide?.();
  }

  triggerSuccessFeedback(): void {
    window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred?.("success");
  }

  close(): void {
    window.Telegram?.WebApp?.close?.();
  }
}
