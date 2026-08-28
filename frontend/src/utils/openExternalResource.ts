import { isTelegramLaunchContext } from "../platform/telegramSdk";

/**
 * Opens a temporary window in a regular browser while the user gesture is
 * still active, then navigates it after the backend returns a signed URL.
 * Telegram Mini Apps must not receive the temporary about:blank URL because
 * their native link confirmation dialog captures it before it can be replaced.
 */
export async function openExternalResource(
  request: Promise<string>,
): Promise<void> {
  const isTelegram = isTelegramLaunchContext();
  const popup = isTelegram ? null : window.open("about:blank", "_blank");
  if (popup) popup.opener = null;

  try {
    const rawUrl = await request;
    let url: URL;
    try {
      url = new URL(rawUrl);
    } catch {
      throw new Error("Разрешены только абсолютные HTTPS-ссылки");
    }
    if (url.protocol !== "https:" || url.username || url.password) {
      throw new Error("Разрешены только абсолютные HTTPS-ссылки");
    }

    if (isTelegram && window.Telegram?.WebApp?.openLink) {
      window.Telegram.WebApp.openLink(url.href);
      return;
    }

    if (popup && !popup.closed) {
      popup.location.replace(url.href);
      return;
    }

    const anchor = document.createElement("a");
    anchor.href = url.href;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.click();
  } catch (error) {
    popup?.close();
    throw error;
  }
}
