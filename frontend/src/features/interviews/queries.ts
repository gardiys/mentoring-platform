import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { InterviewReviewRating } from "../../types/api";

export const interviewKeys = {
  all: ["interviews"] as const,
  decks: ["interviews", "decks"] as const,
  session: (slug: string) => ["interviews", "session", slug] as const,
  topics: (slug: string) => ["interviews", "topics", slug] as const,
};

export function useInterviewDecks() {
  return useQuery({
    queryKey: interviewKeys.decks,
    queryFn: api.interviewDecks,
  });
}

export function useInterviewSession(slug: string) {
  return useQuery({
    queryKey: interviewKeys.session(slug),
    queryFn: () => api.interviewSession(slug),
  });
}

export function useInterviewTopics(slug: string) {
  return useQuery({
    queryKey: interviewKeys.topics(slug),
    queryFn: () => api.interviewTopics(slug),
  });
}

export function useUpdateInterviewTopics() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      deckSlug,
      categories,
    }: {
      deckSlug: string;
      categories: string[];
    }) => api.updateInterviewTopics(deckSlug, categories),
    onSuccess: async (_topics, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: interviewKeys.decks }),
        queryClient.invalidateQueries({
          queryKey: interviewKeys.session(variables.deckSlug),
        }),
        queryClient.invalidateQueries({
          queryKey: interviewKeys.topics(variables.deckSlug),
        }),
      ]);
    },
  });
}

export function useReviewInterviewCard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      cardId,
      rating,
    }: {
      cardId: string;
      rating: InterviewReviewRating;
    }) => api.reviewInterviewCard(cardId, rating),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: interviewKeys.all });
    },
  });
}
