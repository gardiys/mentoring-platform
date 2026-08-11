/**
 * Opens a temporary window while the user gesture is still active, then
 * navigates it after the backend returns a short-lived signed URL. This avoids
 * browsers treating the delayed navigation as an unsolicited popup.
 */
export async function openExternalResource(
  request: Promise<string>,
): Promise<void> {
  const popup = window.open("about:blank", "_blank");
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
