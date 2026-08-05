import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  AdminKnowledgeEntryMutation,
  AdminKnowledgeTopicMutation,
  AdminKnowledgeTopicSettingsMutation,
} from "../../types/api";
import { hasPreparingContentMedia } from "../../utils/contentMedia";

export const adminKnowledgeKeys = {
  all: ["admin", "knowledge"] as const,
  detail: (id: string) => ["admin", "knowledge", id] as const,
  entry: (topicId: string, entryId: string) =>
    ["admin", "knowledge", topicId, "entry", entryId] as const,
};

export function useAdminKnowledgeTopics() {
  return useQuery({
    queryKey: adminKnowledgeKeys.all,
    queryFn: api.adminKnowledgeTopicSummaries,
  });
}

export function useAdminKnowledgeTopic(id: string) {
  return useQuery({
    queryKey: adminKnowledgeKeys.detail(id),
    queryFn: () => api.adminKnowledgeTopicOutline(id),
  });
}

export function useAdminKnowledgeEntry(topicId: string, entryId?: string) {
  return useQuery({
    queryKey: adminKnowledgeKeys.entry(topicId, entryId ?? "new"),
    queryFn: () => api.adminKnowledgeEntry(topicId, entryId!),
    enabled: Boolean(entryId),
    refetchInterval: (query) =>
      hasPreparingContentMedia(query.state.data?.media) ? 5_000 : false,
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

export function useUpdateAdminKnowledgeTopicSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: AdminKnowledgeTopicSettingsMutation;
    }) => api.updateAdminKnowledgeTopicSettings(id, payload),
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

export function useSaveAdminKnowledgeEntry() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      topicId,
      entryId,
      payload,
    }: {
      topicId: string;
      entryId?: string;
      payload: AdminKnowledgeEntryMutation;
    }) =>
      entryId
        ? api.updateAdminKnowledgeEntry(topicId, entryId, payload)
        : api.createAdminKnowledgeEntry(topicId, payload),
    onSuccess: async (_entry, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminKnowledgeKeys.all }),
        queryClient.invalidateQueries({
          queryKey: adminKnowledgeKeys.detail(variables.topicId),
        }),
        queryClient.invalidateQueries({ queryKey: ["knowledge"] }),
      ]);
    },
  });
}
