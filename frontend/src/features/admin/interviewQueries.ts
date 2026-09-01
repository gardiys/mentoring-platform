import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  AdminInterviewCardMutation,
  AdminInterviewDeckMutation,
  AdminInterviewDeckSettingsMutation,
} from "../../types/api";

export const adminInterviewKeys = {
  all: ["admin", "interviews"] as const,
  detail: (id: string) => ["admin", "interviews", id] as const,
  cards: (id: string, query: string, page: number) =>
    ["admin", "interviews", id, "cards", query, page] as const,
  card: (deckId: string, cardId: string) =>
    ["admin", "interviews", deckId, "card", cardId] as const,
};

const PROCESS_PAGE_SIZE = 12;

export function useAdminInterviewDecks(enabled = true) {
  return useQuery({
    queryKey: adminInterviewKeys.all,
    queryFn: api.adminInterviewDeckSummaries,
    enabled,
  });
}

export function useAdminInterviewProcesses(page: number, enabled = true) {
  return useQuery({
    queryKey: [...adminInterviewKeys.all, "processes", page],
    queryFn: () =>
      api.adminInterviewProcesses("all", {
        limit: PROCESS_PAGE_SIZE,
        offset: (page - 1) * PROCESS_PAGE_SIZE,
      }),
    enabled,
  });
}

export function useDeleteAdminInterviewProcess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.deleteAdminInterviewProcess,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminInterviewKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["interviews"] }),
        queryClient.invalidateQueries({ queryKey: ["mentor"] }),
      ]);
    },
  });
}

export function useDeleteAdminInterviewStage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      processId,
      stageId,
    }: {
      processId: string;
      stageId: string;
    }) => api.deleteAdminInterviewStage(processId, stageId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminInterviewKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["interviews"] }),
        queryClient.invalidateQueries({ queryKey: ["mentor"] }),
      ]);
    },
  });
}

export function useAdminInterviewDeck(id: string) {
  return useQuery({
    queryKey: adminInterviewKeys.detail(id),
    queryFn: () => api.adminInterviewDeckOverview(id),
  });
}

export function useAdminInterviewCards(
  id: string,
  query: string,
  page: number,
) {
  return useQuery({
    queryKey: adminInterviewKeys.cards(id, query, page),
    queryFn: () =>
      api.adminInterviewCards(id, {
        query,
        limit: 50,
        offset: (page - 1) * 50,
      }),
  });
}

export function useAdminInterviewCard(deckId: string, cardId?: string) {
  return useQuery({
    queryKey: adminInterviewKeys.card(deckId, cardId ?? "new"),
    queryFn: () => api.adminInterviewCard(deckId, cardId!),
    enabled: Boolean(cardId),
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

export function useUpdateAdminInterviewDeckSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: AdminInterviewDeckSettingsMutation;
    }) => api.updateAdminInterviewDeckSettings(id, payload),
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

export function useSaveAdminInterviewCard() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      deckId,
      cardId,
      payload,
    }: {
      deckId: string;
      cardId?: string;
      payload: AdminInterviewCardMutation;
    }) =>
      cardId
        ? api.updateAdminInterviewCard(deckId, cardId, payload)
        : api.createAdminInterviewCard(deckId, payload),
    onSuccess: async (_card, variables) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: adminInterviewKeys.detail(variables.deckId),
        }),
        queryClient.invalidateQueries({
          queryKey: ["admin", "interviews", variables.deckId, "cards"],
        }),
        queryClient.invalidateQueries({ queryKey: adminInterviewKeys.all }),
        queryClient.invalidateQueries({ queryKey: ["interviews"] }),
      ]);
    },
  });
}
