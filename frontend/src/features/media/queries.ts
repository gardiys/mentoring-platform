import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { UploadOptions } from "../../api/client";
import type {
  AdminKnowledgeEntryRead,
  AdminTopicRead,
  ContentMediaPlayback,
  ProtectedContentMediaRead,
} from "../../types/api";
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
  const refresh = () => {
    if (!entryId) return;
    void Promise.all([
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
    onSuccess: (item) => {
      if (entryId) {
        queryClient.setQueryData<AdminKnowledgeEntryRead>(
          adminKnowledgeKeys.entry(topicId, entryId),
          (current) =>
            current
              ? { ...current, media: mediaWithItem(current.media, item) }
              : current,
        );
      }
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (mediaId: string) => {
      if (!entryId) throw new Error("Сначала сохраните материал");
      return api.deleteAdminKnowledgeMedia(topicId, entryId, mediaId);
    },
    onSuccess: refresh,
  });
  const retry = useMutation({
    mutationFn: (mediaId: string) =>
      api.retryAdminContentMediaNormalization(mediaId),
    onSuccess: (item) => {
      if (entryId) {
        queryClient.setQueryData<AdminKnowledgeEntryRead>(
          adminKnowledgeKeys.entry(topicId, entryId),
          (current) =>
            current
              ? { ...current, media: mediaWithItem(current.media, item) }
              : current,
        );
      }
      refresh();
    },
  });
  return { upload, remove, retry };
}

function mediaWithItem(
  media: ProtectedContentMediaRead[],
  item: ProtectedContentMediaRead,
) {
  return [...media.filter((current) => current.id !== item.id), item].sort(
    (left, right) => left.position - right.position,
  );
}

export function useAdminRoadmapTopicMedia(
  roadmapId: string,
  sectionId: string,
  topicId?: string,
) {
  const queryClient = useQueryClient();
  const refresh = () => {
    if (!topicId) return;
    void Promise.all([
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
    onSuccess: (item) => {
      if (topicId) {
        queryClient.setQueryData<AdminTopicRead>(
          adminRoadmapKeys.topic(roadmapId, sectionId, topicId),
          (current) =>
            current
              ? { ...current, media: mediaWithItem(current.media, item) }
              : current,
        );
      }
      refresh();
    },
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
  const retry = useMutation({
    mutationFn: (mediaId: string) =>
      api.retryAdminContentMediaNormalization(mediaId),
    onSuccess: (item) => {
      if (topicId) {
        queryClient.setQueryData<AdminTopicRead>(
          adminRoadmapKeys.topic(roadmapId, sectionId, topicId),
          (current) =>
            current
              ? { ...current, media: mediaWithItem(current.media, item) }
              : current,
        );
      }
      refresh();
    },
  });
  return { upload, remove, retry };
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
