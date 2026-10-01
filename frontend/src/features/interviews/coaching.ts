import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { notifications } from "@mantine/notifications";
import { apiRequest } from "../../api/client";
import { intelligenceKeys } from "./intelligenceQueries";
import type {
  CommunicationSkill,
  IntelligenceCommunicationDimension,
} from "../../types/api";

export interface CoachingObservation extends IntelligenceCommunicationDimension {
  interview_id: string;
  analysis_revision: number;
  date: string;
  interview_type: string;
  completed_at: string | null;
  decision?: "approved" | "rejected" | null;
}
export function useCoachingHistory(studentId?: string) {
  return useQuery({
    queryKey: ["communication-history", studentId],
    queryFn: () =>
      apiRequest<{
        observations: CoachingObservation[];
        interview_count: number;
        limit: number;
        truncated: boolean;
      }>(`/api/v1/interviews/communication-history/${studentId}`),
    enabled: !!studentId,
    staleTime: 60_000,
  });
}
export function useCoachingAction() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      interviewId,
      skill,
      revision,
      action,
    }: {
      interviewId: string;
      skill: CommunicationSkill;
      revision: number;
      action: "complete" | "uncomplete" | "approve" | "reject";
    }) =>
      apiRequest(`/api/v1/interviews/${interviewId}/communication/${skill}`, {
        method: "PUT",
        body: JSON.stringify({ revision, action }),
      }),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["communication-history"] }),
        client.invalidateQueries({ queryKey: intelligenceKeys.all }),
      ]);
    },
    onError: (e: Error) =>
      notifications.show({ color: "red", message: e.message }),
  });
}

export function useAddInterviewPractice() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      interviewId,
      questionId,
    }: {
      interviewId: string;
      questionId: string;
    }) =>
      apiRequest(
        `/api/v1/interviews/${interviewId}/questions/${questionId}/practice`,
        { method: "POST" },
      ),
    onSuccess: async () => {
      await client.invalidateQueries({
        queryKey: ["card-automation", "personal-review"],
      });
      notifications.show({
        color: "green",
        message: "Вопрос добавлен в повторение",
      });
    },
    onError: (e: Error) =>
      notifications.show({ color: "red", message: e.message }),
  });
}
