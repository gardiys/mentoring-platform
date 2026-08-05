import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import { hasPreparingContentMedia } from "../../utils/contentMedia";

export const knowledgeKeys = {
  topics: ["knowledge", "topics"] as const,
  topic: (slug: string) => ["knowledge", "topics", slug] as const,
  entry: (slug: string) => ["knowledge", "entries", slug] as const,
  search: (query: string) => ["knowledge", "search", query] as const,
};

export function useKnowledgeTopics() {
  return useQuery({
    queryKey: knowledgeKeys.topics,
    queryFn: api.knowledgeTopics,
  });
}

export function useKnowledgeTopic(slug: string) {
  return useQuery({
    queryKey: knowledgeKeys.topic(slug),
    queryFn: () => api.knowledgeTopic(slug),
  });
}

export function useKnowledgeEntry(slug: string) {
  return useQuery({
    queryKey: knowledgeKeys.entry(slug),
    queryFn: () => api.knowledgeEntry(slug),
    refetchInterval: (query) =>
      hasPreparingContentMedia(query.state.data?.media) ? 5_000 : false,
  });
}

export function useKnowledgeSearch(query: string) {
  return useQuery({
    queryKey: knowledgeKeys.search(query),
    queryFn: () => api.knowledgeSearch(query),
    enabled: query.length >= 2,
  });
}
