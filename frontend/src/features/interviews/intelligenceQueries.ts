import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";

export const intelligenceKeys = {
  all: ["interviews", "intelligence"] as const,
  list: (scope: string, status = "all") =>
    ["interviews", "intelligence", scope, status] as const,
  detail: (id: string) => ["interviews", "intelligence", id] as const,
  moderation: (status: string, query: string, offset: number) =>
    ["interviews", "intelligence", "moderation", status, query, offset] as const,
  moderationDetail: (id: string) =>
    ["interviews", "intelligence", "moderation", id] as const,
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

export function useIntelligenceInterviews(enabled = true) {
  return useQuery({
    queryKey: intelligenceKeys.list("own"),
    queryFn: () => api.intelligenceInterviews(),
    enabled,
  });
}

export function useMentorIntelligenceInterviews(
  status: "needs_review" | "reviewed" | "processing" | "all",
) {
  return useQuery({
    queryKey: intelligenceKeys.list("mentor", status),
    queryFn: () => api.mentorIntelligenceInterviews(status),
  });
}

export function useIntelligenceInterview(id: string) {
  return useQuery({
    queryKey: intelligenceKeys.detail(id),
    queryFn: () => api.intelligenceInterview(id),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.processing_status;
      return status &&
        !["ready", "failed", "awaiting_candidate_speaker"].includes(status)
        ? 3_000
        : false;
    },
  });
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
