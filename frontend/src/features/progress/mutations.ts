import { useMutation, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { ProgressStatus } from "../../types/api";
import { roadmapKeys } from "../roadmaps/queries";

export function useUpdateProgress(topicId: string, roadmapSlug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (status: ProgressStatus) => api.updateProgress(topicId, status),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: roadmapKeys.topic(topicId) }),
        queryClient.invalidateQueries({
          queryKey: roadmapKeys.detail(roadmapSlug),
        }),
        queryClient.invalidateQueries({ queryKey: roadmapKeys.all }),
      ]);
    },
  });
}
