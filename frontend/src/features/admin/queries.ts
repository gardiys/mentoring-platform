import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  AdminRoadmapCreate,
  AdminRoadmapUpdate,
  AdminTrackMutation,
} from "../../types/api";

export const adminRoadmapKeys = {
  all: ["admin", "roadmaps"] as const,
  detail: (id: string) => ["admin", "roadmaps", id] as const,
};

export function useAdminRoadmaps() {
  return useQuery({
    queryKey: adminRoadmapKeys.all,
    queryFn: api.adminRoadmaps,
  });
}

export function useAdminRoadmap(id: string) {
  return useQuery({
    queryKey: adminRoadmapKeys.detail(id),
    queryFn: () => api.adminRoadmap(id),
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
