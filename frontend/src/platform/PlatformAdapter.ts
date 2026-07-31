export interface PlatformAdapter {
  readonly platform: "browser" | "telegram";
  readonly isTelegram: boolean;

  getTelegramInitData(): string | null;
  initialize(): void;
  getColorScheme(): "light" | "dark" | null;
  onThemeChange(callback: (scheme: "light" | "dark") => void): () => void;
  onBackButton(callback: () => void): () => void;
  showBackButton(): void;
  hideBackButton(): void;
  triggerSuccessFeedback(): void;
  close(): void;
}
