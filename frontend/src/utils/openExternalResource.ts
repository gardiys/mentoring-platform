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
    const url = await request;
    if (popup && !popup.closed) {
      popup.location.replace(url);
      return;
    }

    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    anchor.click();
  } catch (error) {
    popup?.close();
    throw error;
  }
}
