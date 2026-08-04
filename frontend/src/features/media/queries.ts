import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { UploadOptions } from "../../api/client";
import type { ContentMediaPlayback } from "../../types/api";
import { adminKnowledgeKeys } from "../admin/knowledgeQueries";
import { adminRoadmapKeys } from "../admin/queries";
import { roadmapKeys } from "../roadmaps/queries";

export interface ContentMediaUploadVariables {
  file: File;
  title: string | null;
  position: number;
  options?: UploadOptions;
}

export function useAdminKnowledgeMedia(topicId: string, entryId?: string) {
  const queryClient = useQueryClient();
  const refresh = async () => {
    if (!entryId) return;
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: adminKnowledgeKeys.entry(topicId, entryId),
      }),
      queryClient.invalidateQueries({
        queryKey: adminKnowledgeKeys.detail(topicId),
      }),
      queryClient.invalidateQueries({ queryKey: ["knowledge"] }),
    ]);
  };
  const upload = useMutation({
    mutationFn: ({
      file,
      title,
      position,
      options,
    }: ContentMediaUploadVariables) => {
      if (!entryId) throw new Error("Сначала сохраните материал");
      return api.uploadAdminKnowledgeMedia(
        topicId,
        entryId,
        file,
        { title, position },
        options,
      );
    },
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (mediaId: string) => {
      if (!entryId) throw new Error("Сначала сохраните материал");
      return api.deleteAdminKnowledgeMedia(topicId, entryId, mediaId);
    },
    onSuccess: refresh,
  });
  return { upload, remove };
}

export function useAdminRoadmapTopicMedia(
  roadmapId: string,
  sectionId: string,
  topicId?: string,
) {
  const queryClient = useQueryClient();
  const refresh = async () => {
    if (!topicId) return;
    await Promise.all([
      queryClient.invalidateQueries({
        queryKey: adminRoadmapKeys.topic(roadmapId, sectionId, topicId),
      }),
      queryClient.invalidateQueries({
        queryKey: adminRoadmapKeys.detail(roadmapId),
      }),
      queryClient.invalidateQueries({ queryKey: roadmapKeys.topic(topicId) }),
      queryClient.invalidateQueries({ queryKey: roadmapKeys.all }),
    ]);
  };
  const upload = useMutation({
    mutationFn: ({
      file,
      title,
      position,
      options,
    }: ContentMediaUploadVariables) => {
      if (!topicId) throw new Error("Сначала сохраните тему");
      return api.uploadAdminRoadmapTopicMedia(
        roadmapId,
        sectionId,
        topicId,
        file,
        { title, position },
        options,
      );
    },
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (mediaId: string) => {
      if (!topicId) throw new Error("Сначала сохраните тему");
      return api.deleteAdminRoadmapTopicMedia(
        roadmapId,
        sectionId,
        topicId,
        mediaId,
      );
    },
    onSuccess: refresh,
  });
  return { upload, remove };
}

export function useProtectedContentMediaPlayback(
  resourceKey: string,
  mediaId: string,
  loadPlayback: () => Promise<ContentMediaPlayback>,
) {
  return useQuery({
    queryKey: ["content-media", "playback", resourceKey, mediaId],
    queryFn: loadPlayback,
    enabled: false,
    retry: false,
    refetchOnWindowFocus: false,
  });
}
