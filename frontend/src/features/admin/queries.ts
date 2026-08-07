import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  AdminRoadmapCreate,
  AdminRoadmapSettingsMutation,
  AdminSectionMutation,
  AdminTopicCreate,
  AdminRoadmapUpdate,
  AdminTrackMutation,
} from "../../types/api";
import { hasPreparingContentMedia } from "../../utils/contentMedia";

export const adminRoadmapKeys = {
  all: ["admin", "roadmaps"] as const,
  detail: (id: string) => ["admin", "roadmaps", id] as const,
  section: (roadmapId: string, sectionId: string) =>
    ["admin", "roadmaps", roadmapId, "section", sectionId] as const,
  topic: (roadmapId: string, sectionId: string, topicId: string) =>
    [
      "admin",
      "roadmaps",
      roadmapId,
      "section",
      sectionId,
      "topic",
      topicId,
    ] as const,
};

export function useAdminRoadmaps() {
  return useQuery({
    queryKey: adminRoadmapKeys.all,
    queryFn: api.adminRoadmapSummaries,
  });
}

export function useAdminRoadmap(id: string) {
  return useQuery({
    queryKey: adminRoadmapKeys.detail(id),
    queryFn: () => api.adminRoadmapOutline(id),
  });
}

export function useAdminRoadmapSection(roadmapId: string, sectionId?: string) {
  return useQuery({
    queryKey: adminRoadmapKeys.section(roadmapId, sectionId ?? "new"),
    queryFn: () => api.adminRoadmapSection(roadmapId, sectionId!),
    enabled: Boolean(sectionId),
  });
}

export function useAdminRoadmapTopic(
  roadmapId: string,
  sectionId: string,
  topicId?: string,
) {
  return useQuery({
    queryKey: adminRoadmapKeys.topic(roadmapId, sectionId, topicId ?? "new"),
    queryFn: () => api.adminRoadmapTopic(roadmapId, sectionId, topicId!),
    enabled: Boolean(topicId),
    refetchInterval: (query) =>
      hasPreparingContentMedia(query.state.data?.media) ? 5_000 : false,
  });
}

export function useCreateAdminRoadmap() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AdminRoadmapCreate) =>
      api.createAdminRoadmap(payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminRoadmapKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["roadmaps"] }),
      ]);
    },
  });
}

export function useUpdateAdminRoadmap() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: AdminRoadmapUpdate;
    }) => api.updateAdminRoadmap(id, payload),
    onSuccess: async (roadmap) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminRoadmapKeys.all }),
        queryClient.invalidateQueries({
          queryKey: adminRoadmapKeys.detail(roadmap.id),
        }),
        queryClient.invalidateQueries({ queryKey: ["roadmaps"] }),
      ]);
    },
  });
}

export function useUpdateAdminRoadmapSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: AdminRoadmapSettingsMutation;
    }) => api.updateAdminRoadmapSettings(id, payload),
    onSuccess: async (roadmap) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminRoadmapKeys.all }),
        queryClient.invalidateQueries({
          queryKey: adminRoadmapKeys.detail(roadmap.id),
        }),
        queryClient.invalidateQueries({ queryKey: ["roadmaps"] }),
      ]);
    },
  });
}

export function useDeleteAdminRoadmap() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteAdminRoadmap(id),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminRoadmapKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["roadmaps"] }),
      ]);
    },
  });
}

export function useSaveAdminRoadmapSection() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      roadmapId,
      sectionId,
      payload,
    }: {
      roadmapId: string;
      sectionId?: string;
      payload: AdminSectionMutation;
    }) =>
      sectionId
        ? api.updateAdminRoadmapSection(roadmapId, sectionId, payload)
        : api.createAdminRoadmapSection(roadmapId, payload),
    onSuccess: async (_section, variables) => {
      await queryClient.invalidateQueries({
        queryKey: adminRoadmapKeys.detail(variables.roadmapId),
      });
      await queryClient.invalidateQueries({ queryKey: adminRoadmapKeys.all });
    },
  });
}

export function useSaveAdminRoadmapTopic() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      roadmapId,
      sectionId,
      topicId,
      payload,
    }: {
      roadmapId: string;
      sectionId: string;
      topicId?: string;
      payload: AdminTopicCreate;
    }) =>
      topicId
        ? api.updateAdminRoadmapTopic(roadmapId, sectionId, topicId, payload)
        : api.createAdminRoadmapTopic(roadmapId, sectionId, payload),
    onSuccess: async (_topic, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: adminRoadmapKeys.detail(variables.roadmapId),
        }),
        queryClient.invalidateQueries({ queryKey: ["roadmaps"] }),
      ]);
    },
  });
}

export const adminTrackKeys = {
  all: ["admin", "tracks"] as const,
  detail: (id: string) => ["admin", "tracks", id] as const,
  options: ["admin", "tracks", "options"] as const,
};

export function useAdminTracks() {
  return useQuery({ queryKey: adminTrackKeys.all, queryFn: api.adminTracks });
}

export function useAdminTrack(id: string) {
  return useQuery({
    queryKey: adminTrackKeys.detail(id),
    queryFn: () => api.adminTrack(id),
  });
}

export function useAdminTrackOptions() {
  return useQuery({
    queryKey: adminTrackKeys.options,
    queryFn: api.adminTrackOptions,
  });
}

export function useCreateAdminTrack() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AdminTrackMutation) => api.createAdminTrack(payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: adminTrackKeys.all });
    },
  });
}

export function useUpdateAdminTrack() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: AdminTrackMutation;
    }) => api.updateAdminTrack(id, payload),
    onSuccess: async (track) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminTrackKeys.all }),
        queryClient.invalidateQueries({
          queryKey: adminTrackKeys.detail(track.id),
        }),
        queryClient.invalidateQueries({ queryKey: ["roadmaps"] }),
      ]);
    },
  });
}

export function useSetAdminTrackAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      trackId,
      studentId,
      granted,
    }: {
      trackId: string;
      studentId: string;
      granted: boolean;
    }) =>
      granted
        ? api.grantAdminTrackAccess(trackId, studentId)
        : api.revokeAdminTrackAccess(trackId, studentId),
    onSuccess: async (_response, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminTrackKeys.all }),
        queryClient.invalidateQueries({
          queryKey: adminTrackKeys.detail(variables.trackId),
        }),
        queryClient.invalidateQueries({ queryKey: ["roadmaps"] }),
        queryClient.invalidateQueries({ queryKey: ["mentor"] }),
      ]);
    },
  });
}
