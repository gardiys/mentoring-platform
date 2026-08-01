export function telegramMiniAppLink(botUrl: string): string {
  const trimmed = botUrl.trim().replace(/\/$/, "");
  if (!trimmed.startsWith("https://t.me/")) return trimmed;
  if (/[?&]startapp(?:[=&]|$)/.test(trimmed)) return trimmed;
  return `${trimmed}${trimmed.includes("?") ? "&" : "?"}startapp`;
}
