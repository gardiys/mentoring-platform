export function normalizeTelegramUsername(
  username: string | null | undefined,
): string | null {
  const normalized = username?.trim().replace(/^@+/, "") ?? "";
  return normalized || null;
}

export function isValidTelegramUsername(
  username: string | null | undefined,
): boolean {
  const normalized = normalizeTelegramUsername(username);
  return normalized === null || /^[A-Za-z][A-Za-z0-9_]{4,31}$/.test(normalized);
}
