import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  AutomationDecisionFilters,
  AutomationDecisionOverrideMutation,
  AutomationDecisionReviewMutation,
  CardAutomationMetricsFilters,
  CardAutomationSettingsMutation,
  ManagedPersonalReviewMutation,
  PersonalReviewFilters,
  PersonalReviewMutation,
  QuestionClusterActionResult,
  QuestionClusterAnswerGenerationMutation,
  QuestionClusterBulkMutation,
  QuestionClusterCreateCardMutation,
  QuestionClusterDetail,
  QuestionClusterDraftMutation,
  QuestionClusterFilters,
  QuestionClusterLinkCardMutation,
  QuestionClusterMergeMutation,
  QuestionOccurrenceReprocessMutation,
  QuestionClusterSplitMutation,
  QuestionClusterVersionMutation,
} from "../../types/api";

export type CardAutomationScope = "admin" | "mentor";

export const CARD_AUTOMATION_PAGE_SIZE = 20;

export const cardAutomationKeys = {
  all: ["card-automation"] as const,
  scope: (scope: CardAutomationScope) =>
    [...cardAutomationKeys.all, scope] as const,
  clusters: (scope: CardAutomationScope) =>
    [...cardAutomationKeys.scope(scope), "clusters"] as const,
  clusterList: (
    scope: CardAutomationScope,
    filters: QuestionClusterFilters,
    page: number,
  ) => [...cardAutomationKeys.clusters(scope), "list", filters, page] as const,
  cluster: (scope: CardAutomationScope, clusterId: string) =>
    [...cardAutomationKeys.clusters(scope), "detail", clusterId] as const,
  decisions: (scope: CardAutomationScope) =>
    [...cardAutomationKeys.scope(scope), "decisions"] as const,
  decisionList: (
    scope: CardAutomationScope,
    filters: AutomationDecisionFilters,
    page: number,
  ) => [...cardAutomationKeys.decisions(scope), "list", filters, page] as const,
  settings: ["card-automation", "admin", "settings"] as const,
  metrics: (filters: CardAutomationMetricsFilters) =>
    ["card-automation", "admin", "metrics", filters] as const,
  personal: ["card-automation", "personal-review"] as const,
  personalList: (filters: PersonalReviewFilters, page: number) =>
    [...cardAutomationKeys.personal, "list", filters, page] as const,
  managedPersonal: (scope: CardAutomationScope, studentId: string) =>
    [
      ...cardAutomationKeys.scope(scope),
      "students",
      studentId,
      "personal-review",
    ] as const,
  managedPersonalList: (
    scope: CardAutomationScope,
    studentId: string,
    filters: PersonalReviewFilters,
    page: number,
  ) =>
    [
      ...cardAutomationKeys.managedPersonal(scope, studentId),
      "list",
      filters,
      page,
    ] as const,
};

function idempotencyKey(): string {
  return (
    globalThis.crypto?.randomUUID?.() ??
    `${Date.now()}-${Math.random().toString(36).slice(2)}`
  );
}

export function useQuestionClusters(
  filters: QuestionClusterFilters,
  page: number,
  scope: CardAutomationScope = "admin",
) {
  return useQuery({
    queryKey: cardAutomationKeys.clusterList(scope, filters, page),
    queryFn: () =>
      (scope === "admin"
        ? api.adminCardAutomationClusters
        : api.mentorCardAutomationClusters)(filters, {
        limit: CARD_AUTOMATION_PAGE_SIZE,
        offset: (page - 1) * CARD_AUTOMATION_PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  });
}

export function useQuestionCluster(
  clusterId: string,
  scope: CardAutomationScope = "admin",
) {
  return useQuery({
    queryKey: cardAutomationKeys.cluster(scope, clusterId),
    queryFn: () =>
      scope === "admin"
        ? api.adminCardAutomationCluster(clusterId)
        : api.mentorCardAutomationCluster(clusterId),
    enabled: Boolean(clusterId),
  });
}

function useClusterMutation<Payload>(
  scope: CardAutomationScope,
  mutationFn: (
    clusterId: string,
    payload: Payload,
    idempotencyKey: string,
  ) => Promise<QuestionClusterActionResult>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      clusterId,
      payload,
    }: {
      clusterId: string;
      payload: Payload;
    }) => mutationFn(clusterId, payload, idempotencyKey()),
    onSuccess: async ({ cluster }) => {
      queryClient.setQueryData<QuestionClusterDetail>(
        cardAutomationKeys.cluster(scope, cluster.id),
        (current) => (current ? { ...current, ...cluster } : current),
      );
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.cluster(scope, cluster.id),
        }),
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.clusters(scope),
        }),
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.decisions(scope),
        }),
        queryClient.invalidateQueries({
          queryKey: ["interviews", "intelligence"],
        }),
        queryClient.invalidateQueries({ queryKey: ["admin", "interviews"] }),
        queryClient.invalidateQueries({ queryKey: ["interviews", "decks"] }),
      ]);
    },
  });
}

export function useLinkQuestionCluster() {
  return useClusterMutation<QuestionClusterLinkCardMutation>(
    "admin",
    api.linkAdminCardAutomationCluster,
  );
}

export function useCreateCardFromQuestionCluster() {
  return useClusterMutation<QuestionClusterCreateCardMutation>(
    "admin",
    api.createCardFromAdminCardAutomationCluster,
  );
}

export function useGenerateQuestionClusterAnswer() {
  return useMutation({
    mutationFn: ({
      clusterId,
      payload,
    }: {
      clusterId: string;
      payload: QuestionClusterAnswerGenerationMutation;
    }) =>
      api.generateAdminCardAutomationClusterAnswer(
        clusterId,
        payload,
        idempotencyKey(),
      ),
  });
}

export function useUpdateQuestionClusterDraft(
  scope: CardAutomationScope = "admin",
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      clusterId,
      payload,
    }: {
      clusterId: string;
      payload: QuestionClusterDraftMutation;
    }) =>
      (scope === "admin"
        ? api.updateAdminCardAutomationClusterDraft
        : api.updateMentorCardAutomationClusterDraft)(
        clusterId,
        payload,
        idempotencyKey(),
      ),
    onSuccess: async (_result, { clusterId }) => {
      // The mutation response intentionally contains only a cluster summary.
      // Refetch the full detail before changing the version in cache so the
      // reviewed answer contract and all dependent forms stay synchronized.
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.cluster(scope, clusterId),
        }),
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.clusters(scope),
        }),
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.decisions(scope),
        }),
      ]);
    },
  });
}

export function useSplitQuestionCluster() {
  return useClusterMutation<QuestionClusterSplitMutation>(
    "admin",
    api.splitAdminCardAutomationCluster,
  );
}

export function useMergeQuestionCluster() {
  return useClusterMutation<QuestionClusterMergeMutation>(
    "admin",
    api.mergeAdminCardAutomationCluster,
  );
}

export function useSetQuestionClusterState(
  scope: CardAutomationScope = "admin",
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      clusterId,
      action,
      payload,
    }: {
      clusterId: string;
      action: "ignore" | "defer" | "mark-important" | "reopen";
      payload: QuestionClusterVersionMutation;
    }) =>
      (scope === "admin"
        ? api.setAdminCardAutomationClusterState
        : api.setMentorCardAutomationClusterState)(
        clusterId,
        action,
        payload,
        idempotencyKey(),
      ),
    onSuccess: async ({ cluster }) => {
      queryClient.setQueryData<QuestionClusterDetail>(
        cardAutomationKeys.cluster(scope, cluster.id),
        (current) => (current ? { ...current, ...cluster } : current),
      );
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.clusters(scope),
        }),
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.decisions(scope),
        }),
      ]);
    },
  });
}

export function useReprocessQuestionOccurrence(
  scope: CardAutomationScope = "admin",
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      occurrenceId,
      payload,
    }: {
      clusterId: string;
      occurrenceId: string;
      payload: QuestionOccurrenceReprocessMutation;
    }) =>
      (scope === "admin"
        ? api.reprocessAdminCardAutomationOccurrence
        : api.reprocessMentorCardAutomationOccurrence)(
        occurrenceId,
        payload,
        idempotencyKey(),
      ),
    onSuccess: async (_result, { clusterId }) => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.cluster(scope, clusterId),
        }),
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.clusters(scope),
        }),
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.decisions(scope),
        }),
      ]);
    },
  });
}

export function useBulkQuestionClusters() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: QuestionClusterBulkMutation) =>
      api.bulkAdminCardAutomationClusters(payload, idempotencyKey()),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.clusters("admin"),
        }),
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.decisions("admin"),
        }),
        queryClient.invalidateQueries({
          queryKey: ["card-automation", "admin", "metrics"],
        }),
      ]);
    },
  });
}

export function useAutomationDecisions(
  filters: AutomationDecisionFilters,
  page: number,
  scope: CardAutomationScope = "admin",
) {
  return useQuery({
    queryKey: cardAutomationKeys.decisionList(scope, filters, page),
    queryFn: () =>
      (scope === "admin"
        ? api.adminCardAutomationDecisions
        : api.mentorCardAutomationDecisions)(filters, {
        limit: CARD_AUTOMATION_PAGE_SIZE,
        offset: (page - 1) * CARD_AUTOMATION_PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  });
}

export function useReviewAutomationDecision(
  scope: CardAutomationScope = "admin",
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      decisionId,
      payload,
    }: {
      decisionId: string;
      payload: AutomationDecisionReviewMutation;
    }) =>
      (scope === "admin"
        ? api.reviewAdminCardAutomationDecision
        : api.reviewMentorCardAutomationDecision)(
        decisionId,
        payload,
        idempotencyKey(),
      ),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: cardAutomationKeys.decisions(scope),
      });
    },
  });
}

export function useOverrideAutomationDecision(
  scope: CardAutomationScope = "admin",
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      decisionId,
      payload,
    }: {
      decisionId: string;
      payload: AutomationDecisionOverrideMutation;
    }) =>
      (scope === "admin"
        ? api.overrideAdminCardAutomationDecision
        : api.overrideMentorCardAutomationDecision)(
        decisionId,
        payload,
        idempotencyKey(),
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.decisions(scope),
        }),
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.clusters(scope),
        }),
        queryClient.invalidateQueries({
          queryKey: ["interviews", "intelligence"],
        }),
      ]);
    },
  });
}

export function useCardAutomationSettings() {
  return useQuery({
    queryKey: cardAutomationKeys.settings,
    queryFn: api.adminCardAutomationSettings,
  });
}

export function useUpdateCardAutomationSettings() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: CardAutomationSettingsMutation) =>
      api.updateAdminCardAutomationSettings(payload, idempotencyKey()),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: cardAutomationKeys.settings,
      });
    },
  });
}

export function useCardAutomationMetrics(
  filters: CardAutomationMetricsFilters,
  enabled = true,
) {
  return useQuery({
    queryKey: cardAutomationKeys.metrics(filters),
    queryFn: () => api.adminCardAutomationMetrics(filters),
    enabled,
  });
}

export function usePersonalReviewItems(
  filters: PersonalReviewFilters,
  page = 1,
) {
  return useQuery({
    queryKey: cardAutomationKeys.personalList(filters, page),
    queryFn: () =>
      api.personalReviewItems(filters, {
        limit: CARD_AUTOMATION_PAGE_SIZE,
        offset: (page - 1) * CARD_AUTOMATION_PAGE_SIZE,
      }),
    placeholderData: keepPreviousData,
  });
}

export function useManagedPersonalReviewItems(
  scope: CardAutomationScope,
  studentId: string,
  filters: PersonalReviewFilters,
  page = 1,
) {
  return useQuery({
    queryKey: cardAutomationKeys.managedPersonalList(
      scope,
      studentId,
      filters,
      page,
    ),
    queryFn: () =>
      (scope === "admin"
        ? api.adminManagedPersonalReviewItems
        : api.mentorManagedPersonalReviewItems)(studentId, filters, {
        limit: CARD_AUTOMATION_PAGE_SIZE,
        offset: (page - 1) * CARD_AUTOMATION_PAGE_SIZE,
      }),
    enabled: Boolean(studentId),
    placeholderData: keepPreviousData,
  });
}

export function useUpdateManagedPersonalReviewItem(
  scope: CardAutomationScope,
  studentId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      itemId,
      payload,
    }: {
      itemId: string;
      payload: ManagedPersonalReviewMutation;
    }) =>
      (scope === "admin"
        ? api.updateAdminManagedPersonalReviewItem
        : api.updateMentorManagedPersonalReviewItem)(
        studentId,
        itemId,
        payload,
        idempotencyKey(),
      ),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.managedPersonal(scope, studentId),
        }),
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.decisions(scope),
        }),
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.personal,
        }),
      ]);
    },
  });
}

export function useReviewPersonalReviewItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      itemId,
      payload,
    }: {
      itemId: string;
      payload: PersonalReviewMutation;
    }) => api.reviewPersonalReviewItem(itemId, payload, idempotencyKey()),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({
          queryKey: cardAutomationKeys.personal,
        }),
        queryClient.invalidateQueries({ queryKey: ["interviews"] }),
      ]);
    },
  });
}
