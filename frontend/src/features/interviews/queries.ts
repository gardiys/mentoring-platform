import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  InterviewQuestionLearnedFilter,
  InterviewReviewRating,
} from "../../types/api";

export interface InterviewQuestionTableFilters {
  category: string | null;
  frequentOnly: boolean;
  learned: InterviewQuestionLearnedFilter;
  query: string;
  limit: number;
  offset: number;
}

export const interviewKeys = {
  all: ["interviews"] as const,
  decks: ["interviews", "decks"] as const,
  sessionRoot: (slug: string) => ["interviews", "session", slug] as const,
  session: (slug: string, frequentOnly: boolean) =>
    [...interviewKeys.sessionRoot(slug), { frequentOnly }] as const,
  cardSearch: (slug: string, query: string, frequentOnly: boolean) =>
    ["interviews", "card-search", slug, query, { frequentOnly }] as const,
  topics: (slug: string) => ["interviews", "topics", slug] as const,
  questionTableRoot: (slug: string) =>
    ["interviews", "questions", slug] as const,
  questionTable: (slug: string, filters: InterviewQuestionTableFilters) =>
    [...interviewKeys.questionTableRoot(slug), filters] as const,
};

export function useInterviewDecks() {
  return useQuery({
    queryKey: interviewKeys.decks,
    queryFn: api.interviewDecks,
  });
}

export function useInterviewSession(slug: string, frequentOnly = false) {
  return useQuery({
    queryKey: interviewKeys.session(slug, frequentOnly),
    queryFn: () => api.interviewSession(slug, frequentOnly),
  });
}

export function useInterviewCardSearch(
  slug: string,
  query: string,
  frequentOnly = false,
) {
  return useQuery({
    queryKey: interviewKeys.cardSearch(slug, query, frequentOnly),
    queryFn: () => api.searchInterviewCards(slug, query, frequentOnly),
    enabled: query.trim().length >= 2,
  });
}

export function useInterviewTopics(slug: string) {
  return useQuery({
    queryKey: interviewKeys.topics(slug),
    queryFn: () => api.interviewTopics(slug),
  });
}

export function useInterviewQuestionTable(
  slug: string,
  filters: InterviewQuestionTableFilters,
) {
  return useQuery({
    queryKey: interviewKeys.questionTable(slug, filters),
    queryFn: () => api.interviewQuestionTable(slug, filters),
  });
}

export function useSetInterviewQuestionLearned() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ cardId, learned }: { cardId: string; learned: boolean }) =>
      api.setInterviewQuestionLearned(cardId, learned),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: interviewKeys.all });
    },
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
          queryKey: interviewKeys.sessionRoot(variables.deckSlug),
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
