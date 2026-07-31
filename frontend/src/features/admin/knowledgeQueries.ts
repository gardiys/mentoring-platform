import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { AdminKnowledgeTopicMutation } from "../../types/api";

export const adminKnowledgeKeys = {
  all: ["admin", "knowledge"] as const,
  detail: (id: string) => ["admin", "knowledge", id] as const,
};

export function useAdminKnowledgeTopics() {
  return useQuery({
    queryKey: adminKnowledgeKeys.all,
    queryFn: api.adminKnowledgeTopics,
  });
}

export function useAdminKnowledgeTopic(id: string) {
  return useQuery({
    queryKey: adminKnowledgeKeys.detail(id),
    queryFn: () => api.adminKnowledgeTopic(id),
  });
}

export function useCreateAdminKnowledgeTopic() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AdminKnowledgeTopicMutation) =>
      api.createAdminKnowledgeTopic(payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminKnowledgeKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["knowledge"] }),
      ]);
    },
  });
}

export function useUpdateAdminKnowledgeTopic() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: AdminKnowledgeTopicMutation;
    }) => api.updateAdminKnowledgeTopic(id, payload),
    onSuccess: async (topic) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminKnowledgeKeys.all }),
        queryClient.invalidateQueries({
          queryKey: adminKnowledgeKeys.detail(topic.id),
        }),
        queryClient.invalidateQueries({ queryKey: ["knowledge"] }),
      ]);
    },
  });
}
