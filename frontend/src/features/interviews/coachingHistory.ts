import type { CoachingObservation } from "./coaching";

/** Both practice and history show the latest interview first, with a stable tie-breaker. */
export function sortObservations(items: CoachingObservation[]) {
  return [...items].sort(
    (a, b) =>
      Date.parse(b.date) - Date.parse(a.date) ||
      b.interview_id.localeCompare(a.interview_id),
  );
}

export function comparableGroups(observations: CoachingObservation[]) {
  const groups = new Map<string, CoachingObservation[]>();
  for (const item of sortObservations(observations)) {
    if (!item.skill || item.score == null || item.decision === "rejected")
      continue;
    const key = `${item.skill}:${item.interview_type}`;
    const items = groups.get(key) ?? [];
    if (!items.some((existing) => existing.interview_id === item.interview_id))
      items.push(item);
    groups.set(key, items);
  }
  return [...groups.entries()].filter(([, items]) => items.length >= 2);
}
