export function formatRubles(kopecks: number): string {
  return new Intl.NumberFormat("ru-RU", {
    style: "currency",
    currency: "RUB",
    minimumFractionDigits: kopecks % 100 === 0 ? 0 : 2,
  }).format(kopecks / 100);
}
