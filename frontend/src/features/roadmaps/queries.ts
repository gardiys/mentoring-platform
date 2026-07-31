import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";

export const roadmapKeys = {
  all: ["roadmaps"] as const,
  detail: (slug: string) => ["roadmaps", slug] as const,
  topic: (id: string) => ["topics", id] as const,
};

export function useRoadmaps() {
  return useQuery({ queryKey: roadmapKeys.all, queryFn: api.roadmaps });
}

export function useRoadmap(slug: string) {
  return useQuery({
    queryKey: roadmapKeys.detail(slug),
    queryFn: () => api.roadmap(slug),
  });
}

export function useStartRoadmap(slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.startRoadmap(slug),
    onSuccess: async (roadmap) => {
      queryClient.setQueryData(roadmapKeys.detail(slug), roadmap);
      await queryClient.invalidateQueries({
        queryKey: roadmapKeys.all,
        exact: true,
      });
    },
  });
}

export function useTopic(id: string) {
  return useQuery({
    queryKey: roadmapKeys.topic(id),
    queryFn: () => api.topic(id),
  });
}
