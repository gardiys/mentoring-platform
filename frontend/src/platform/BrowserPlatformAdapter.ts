import type { PlatformAdapter } from "./PlatformAdapter";

export class BrowserPlatformAdapter implements PlatformAdapter {
  readonly platform = "browser" as const;
  readonly isTelegram = false;

  getTelegramInitData(): null {
    return null;
  }

  initialize(): void {}
  getColorScheme(): null {
    return null;
  }
  onThemeChange(): () => void {
    return () => undefined;
  }
  onBackButton(): () => void {
    return () => undefined;
  }
  showBackButton(): void {}
  hideBackButton(): void {}
  triggerSuccessFeedback(): void {}
  close(): void {}
}
