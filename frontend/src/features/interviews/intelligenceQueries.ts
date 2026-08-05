import { useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { IntelligenceInterviewDetail } from "../../types/api";

export const intelligenceKeys = {
  all: ["interviews", "intelligence"] as const,
  list: (scope: string, status = "all", page = 1) =>
    ["interviews", "intelligence", scope, status, page] as const,
  detail: (id: string) => ["interviews", "intelligence", id] as const,
  processing: (id: string) =>
    ["interviews", "intelligence", id, "processing"] as const,
  moderation: (status: string, query: string, offset: number) =>
    [
      "interviews",
      "intelligence",
      "moderation",
      status,
      query,
      offset,
    ] as const,
  moderationDetail: (id: string) =>
    ["interviews", "intelligence", "moderation", id] as const,
  operations: ["interviews", "intelligence", "operations"] as const,
};

export function useAdminQuestionModeration(
  status: "needs_review" | "mentor_approved" | "approved" | "rejected" | "all",
  query: string,
  offset: number,
) {
  return useQuery({
    queryKey: intelligenceKeys.moderation(status, query, offset),
    queryFn: () =>
      api.adminQuestionModeration({ status, q: query, limit: 20, offset }),
  });
}

export function useAdminQuestionModerationDetail(id: string) {
  return useQuery({
    queryKey: intelligenceKeys.moderationDetail(id),
    queryFn: () => api.adminQuestionModerationDetail(id),
    enabled: Boolean(id),
  });
}

export function useIntelligenceInterviews(enabled = true, page = 1) {
  return useQuery({
    queryKey: intelligenceKeys.list("own", "all", page),
    queryFn: () =>
      api.intelligenceInterviews({ limit: 6, offset: (page - 1) * 6 }),
    enabled,
    placeholderData: (previous) => previous,
    refetchInterval: (query) => {
      const items = query.state.data?.items ?? [];
      if (
        items.some(
          (item) =>
            ![
              "uploaded",
              "ready",
              "failed",
              "awaiting_candidate_speaker",
            ].includes(item.processing_status),
        )
      )
        return 5_000;
      return items.some((item) => item.processing_status === "uploaded")
        ? 30_000
        : false;
    },
  });
}

export function useMentorIntelligenceInterviews(
  status: "requested" | "needs_review" | "reviewed" | "processing" | "all",
  page = 1,
  enabled = true,
) {
  return useQuery({
    queryKey: intelligenceKeys.list("mentor", status, page),
    queryFn: () =>
      api.mentorIntelligenceInterviews(status, {
        limit: 10,
        offset: (page - 1) * 10,
      }),
    enabled,
    placeholderData: (previous, previousQuery) =>
      previousQuery?.queryKey[3] === status ? previous : undefined,
    refetchInterval: (query) =>
      query.state.data?.items.some(
        (item) =>
          !["ready", "failed", "awaiting_candidate_speaker"].includes(
            item.processing_status,
          ),
      )
        ? status === "requested"
          ? 15_000
          : 5_000
        : 15_000,
  });
}

export function useAdminIntelligenceOperations(enabled: boolean) {
  return useQuery({
    queryKey: intelligenceKeys.operations,
    queryFn: api.adminIntelligenceOperations,
    enabled,
    refetchInterval: 15_000,
  });
}

export function useIntelligenceInterview(id: string) {
  const queryClient = useQueryClient();
  const detail = useQuery({
    queryKey: intelligenceKeys.detail(id),
    queryFn: () => api.intelligenceInterview(id),
    enabled: Boolean(id),
  });
  const status = detail.data?.processing_status;
  const shouldPoll = Boolean(
    status &&
    !["ready", "failed", "awaiting_candidate_speaker"].includes(status),
  );
  const processing = useQuery({
    queryKey: intelligenceKeys.processing(id),
    queryFn: () => api.intelligenceInterviewProcessing(id),
    enabled: Boolean(id) && shouldPoll,
    refetchInterval: (query) => {
      const processingStatus = query.state.data?.status;
      if (processingStatus === "uploaded") return 30_000;
      return processingStatus &&
        !["ready", "failed", "awaiting_candidate_speaker"].includes(
          processingStatus,
        )
        ? 3_000
        : false;
    },
  });

  useEffect(() => {
    const progress = processing.data;
    if (!progress || processing.dataUpdatedAt < detail.dataUpdatedAt) return;
    queryClient.setQueryData<IntelligenceInterviewDetail>(
      intelligenceKeys.detail(id),
      (current) => {
        if (!current) return current;
        return {
          ...current,
          processing_status: progress.status,
          processing: progress,
        };
      },
    );
    if (
      ["ready", "failed", "awaiting_candidate_speaker"].includes(
        progress.status,
      )
    ) {
      void queryClient.invalidateQueries({
        queryKey: intelligenceKeys.detail(id),
        exact: true,
      });
    }
  }, [
    detail.dataUpdatedAt,
    id,
    processing.data,
    processing.dataUpdatedAt,
    queryClient,
  ]);

  return detail;
}

function useIntelligenceMutation<TVariables, TData>(
  mutationFn: (variables: TVariables) => Promise<TData>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: async () => {
      await queryClient.invalidateQueries({ queryKey: intelligenceKeys.all });
    },
  });
}

export function useSelectIntelligenceCandidate() {
  return useIntelligenceMutation(
    ({ interviewId, speakerId }: { interviewId: string; speakerId: string }) =>
      api.selectIntelligenceCandidate(interviewId, speakerId),
  );
}

export function useRetryIntelligenceInterview() {
  return useIntelligenceMutation((id: string) =>
    api.retryIntelligenceInterview(id),
  );
}

export function useAdminRequeueIntelligenceInterview() {
  return useIntelligenceMutation((id: string) =>
    api.adminRequeueIntelligenceInterview(id),
  );
}

export function useDeleteIntelligenceInterview() {
  return useIntelligenceMutation((id: string) =>
    api.deleteIntelligenceInterview(id),
  );
}

export function useIntelligenceReviewAction() {
  return useIntelligenceMutation(
    ({
      interviewId,
      reviewId,
      action,
    }: {
      interviewId: string;
      reviewId: string;
      action: "approve" | "reject";
    }) =>
      action === "approve"
        ? api.approveIntelligenceReview(interviewId, reviewId)
        : api.rejectIntelligenceReview(interviewId, reviewId),
  );
}

export function useIntelligenceQuestionModeration() {
  return useIntelligenceMutation(
    ({
      interviewId,
      questionId,
      payload,
    }: {
      interviewId: string;
      questionId: string;
      payload: Parameters<typeof api.moderateIntelligenceQuestion>[2];
    }) => api.moderateIntelligenceQuestion(interviewId, questionId, payload),
  );
}

export function useCompleteIntelligenceReview() {
  return useIntelligenceMutation((id: string) =>
    api.completeIntelligenceReview(id),
  );
}

export function useGenerateIntelligenceOverview() {
  return useIntelligenceMutation((id: string) =>
    api.generateIntelligenceOverview(id),
  );
}

export function useAddIntelligenceComment() {
  return useIntelligenceMutation(
    ({ interviewId, text }: { interviewId: string; text: string }) =>
      api.addIntelligenceMentorComment(interviewId, { text }),
  );
}
