const DEV_USER_KEY = "mentoring.dev-user-id";

export function getDevUserId(): string | null {
  return localStorage.getItem(DEV_USER_KEY);
}

export function setDevUserId(userId: string): void {
  localStorage.setItem(DEV_USER_KEY, userId);
}

export function clearDevUserId(): void {
  localStorage.removeItem(DEV_USER_KEY);
}
