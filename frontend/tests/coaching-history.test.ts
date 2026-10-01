import { expect, it } from "vitest";
import {
  comparableGroups,
  sortObservations,
} from "../src/features/interviews/coachingHistory";
import type { CoachingObservation } from "../src/features/interviews/coaching";

function observation(
  id: string,
  date: string,
  score: number | null,
  decision: CoachingObservation["decision"] = null,
): CoachingObservation {
  return {
    interview_id: id,
    date,
    score,
    decision,
    skill: "structure",
    name: "Структура ответа",
    confidence: 0.9,
    summary: "Пример",
    evidence_utterance_ids: [],
    analysis_revision: 1,
    interview_type: "hr",
    completed_at: null,
  };
}

it("sorts newest first explicitly, breaks date ties by id without mutating input", () => {
  const items = [
    observation("a", "2026-08-01", 0.3),
    observation("c", "2026-09-01", 0.35),
    observation("b", "2026-09-01", 0.9),
  ];
  expect(sortObservations(items).map((i) => i.interview_id)).toEqual([
    "c",
    "b",
    "a",
  ]);
  expect(items[0]!.interview_id).toBe("a");
  expect(comparableGroups(items)[0]![1].map((i) => i.score)).toEqual([
    0.35, 0.9, 0.3,
  ]);
});

it("requires two distinct, scored, non-rejected interviews of the same format", () => {
  const first = observation("a", "2026-08-01", 0.4);
  const rejected = observation("b", "2026-09-01", 0.1, "rejected");
  expect(
    comparableGroups([
      first,
      first,
      rejected,
      observation("c", "2026-09-02", null),
    ]),
  ).toEqual([]);
  expect(
    comparableGroups([
      first,
      { ...observation("b", "2026-09-01", 0.9), interview_type: "technical" },
    ]),
  ).toEqual([]);
  expect(
    comparableGroups([first, observation("b", "2026-09-01", 0.9, "approved")]),
  ).toHaveLength(1);
});
