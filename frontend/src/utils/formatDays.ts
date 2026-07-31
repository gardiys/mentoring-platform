export function formatDays(days: number): string {
  const mod100 = Math.abs(days) % 100;
  const mod10 = mod100 % 10;
  const suffix =
    mod100 >= 11 && mod100 <= 14
      ? "дней"
      : mod10 === 1
        ? "день"
        : mod10 >= 2 && mod10 <= 4
          ? "дня"
          : "дней";
  return `${days} ${suffix}`;
}
