import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { UploadOptions } from "../../api/client";
import type {
  InterviewProcessMutation,
  InterviewProcessOutcomeMutation,
  InterviewProcessRecruitersMutation,
  InterviewProcessStageMutation,
  InterviewProcessStatus,
} from "../../types/api";
import { interviewCatalogKeys } from "./catalogQueries";

export const interviewJournalKeys = {
  all: ["interviews", "journal"] as const,
  list: (status: InterviewProcessStatus | "all") =>
    ["interviews", "journal", "list", status] as const,
  detail: (id: string) => ["interviews", "journal", id] as const,
  companies: (query: string) =>
    ["interviews", "journal", "companies", query] as const,
  directions: ["interviews", "journal", "directions"] as const,
};

export function useInterviewDirections() {
  return useQuery({
    queryKey: interviewJournalKeys.directions,
    queryFn: api.interviewDirections,
    staleTime: 5 * 60_000,
  });
}

export function useInterviewCompanySuggestions(query: string) {
  return useQuery({
    queryKey: interviewJournalKeys.companies(query),
    queryFn: () => api.interviewCompanySuggestions(query),
    enabled: Boolean(query.trim()),
    staleTime: 60_000,
  });
}

export function useInterviewProcesses(
  status: InterviewProcessStatus | "all" = "all",
  enabled = true,
) {
  return useQuery({
    queryKey: interviewJournalKeys.list(status),
    queryFn: () => api.interviewProcesses(status),
    enabled,
  });
}

export function useInterviewProcess(id: string) {
  return useQuery({
    queryKey: interviewJournalKeys.detail(id),
    queryFn: () => api.interviewProcess(id),
    enabled: Boolean(id),
  });
}

function useJournalMutation<TVariables, TData>(
  mutationFn: (variables: TVariables) => Promise<TData>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: interviewJournalKeys.all }),
        queryClient.invalidateQueries({ queryKey: interviewCatalogKeys.all }),
      ]);
    },
  });
}

export function useCreateInterviewProcess() {
  return useJournalMutation((payload: InterviewProcessMutation) =>
    api.createInterviewProcess(payload),
  );
}

export function useUpdateInterviewProcess() {
  return useJournalMutation(
    ({ id, payload }: { id: string; payload: InterviewProcessMutation }) =>
      api.updateInterviewProcess(id, payload),
  );
}

export function useSetInterviewProcessOutcome() {
  return useJournalMutation(
    ({
      id,
      payload,
    }: {
      id: string;
      payload: InterviewProcessOutcomeMutation;
    }) => api.setInterviewProcessOutcome(id, payload),
  );
}

export function useSetInterviewProcessRecruiters() {
  return useJournalMutation(
    ({
      id,
      payload,
    }: {
      id: string;
      payload: InterviewProcessRecruitersMutation;
    }) => api.setInterviewProcessRecruiters(id, payload),
  );
}

export function useCreateInterviewStage() {
  return useJournalMutation(
    ({
      processId,
      payload,
    }: {
      processId: string;
      payload: InterviewProcessStageMutation;
    }) => api.createInterviewProcessStage(processId, payload),
  );
}

export function useStartInterviewStageAnalysis() {
  return useJournalMutation(
    ({ processId, stageId }: { processId: string; stageId: string }) =>
      api.startInterviewStageAnalysis(processId, stageId),
  );
}

export function useUploadInterviewStageMedia() {
  return useJournalMutation(
    ({
      processId,
      stageId,
      file,
      onProgress,
      signal,
    }: {
      processId: string;
      stageId: string;
      file: File;
      onProgress?: UploadOptions["onProgress"];
      signal?: AbortSignal;
    }) =>
      api.uploadInterviewStageMedia(processId, stageId, file, {
        onProgress,
        signal,
      }),
  );
}

export function useUploadInterviewStageAttachments() {
  return useJournalMutation(
    async ({
      processId,
      stageId,
      files,
    }: {
      processId: string;
      stageId: string;
      files: File[];
    }) => {
      for (const file of files) {
        await api.uploadInterviewStageAttachment(processId, stageId, file);
      }
      return api.interviewProcess(processId);
    },
  );
}

export function useDeleteInterviewStageAttachment() {
  return useJournalMutation(
    ({
      processId,
      stageId,
      attachmentId,
    }: {
      processId: string;
      stageId: string;
      attachmentId: string;
    }) => api.deleteInterviewStageAttachment(processId, stageId, attachmentId),
  );
}

export function useMarkInterviewOffer() {
  return useJournalMutation(
    async ({ processId, file }: { processId: string; file?: File | null }) => {
      await api.setInterviewProcessOutcome(processId, { status: "offer" });
      if (file) {
        try {
          return await api.uploadInterviewOffer(processId, file);
        } catch (error) {
          const reason = error instanceof Error ? ` ${error.message}` : "";
          throw new Error(
            `Оффер отмечен, но файл не загрузился.${reason} Повторите загрузку файла в открывшемся блоке оффера.`,
            { cause: error },
          );
        }
      }
      return api.interviewProcess(processId);
    },
  );
}

export function useCancelInterviewOffer() {
  return useJournalMutation(({ processId }: { processId: string }) =>
    api.deleteInterviewOffer(processId),
  );
}
