import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { AdminInterviewDeckMutation } from "../../types/api";

export const adminInterviewKeys = {
  all: ["admin", "interviews"] as const,
  detail: (id: string) => ["admin", "interviews", id] as const,
};

export function useAdminInterviewDecks() {
  return useQuery({
    queryKey: adminInterviewKeys.all,
    queryFn: api.adminInterviewDecks,
  });
}

export function useAdminInterviewDeck(id: string) {
  return useQuery({
    queryKey: adminInterviewKeys.detail(id),
    queryFn: () => api.adminInterviewDeck(id),
  });
}

export function useCreateAdminInterviewDeck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AdminInterviewDeckMutation) =>
      api.createAdminInterviewDeck(payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminInterviewKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["interviews"] }),
      ]);
    },
  });
}

export function useUpdateAdminInterviewDeck() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: AdminInterviewDeckMutation;
    }) => api.updateAdminInterviewDeck(id, payload),
    onSuccess: async (deck) => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminInterviewKeys.all }),
        queryClient.invalidateQueries({
          queryKey: adminInterviewKeys.detail(deck.id),
        }),
        queryClient.invalidateQueries({ queryKey: ["interviews"] }),
      ]);
    },
  });
}
