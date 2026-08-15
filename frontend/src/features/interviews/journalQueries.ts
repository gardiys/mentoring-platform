import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import { ApiError, type UploadOptions } from "../../api/client";
import type {
  InterviewProcessMutation,
  InterviewProcessOutcomeMutation,
  InterviewProcessRecruitersMutation,
  InterviewProcessDetail,
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
    onSuccess: (data) => {
      if (isInterviewProcessDetail(data)) {
        queryClient.setQueryData(interviewJournalKeys.detail(data.id), data);
      }
    },
    onSettled: () => {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: interviewJournalKeys.all }),
        queryClient.invalidateQueries({ queryKey: interviewCatalogKeys.all }),
      ]);
    },
  });
}

function isInterviewProcessDetail(
  value: unknown,
): value is InterviewProcessDetail {
  return (
    typeof value === "object" &&
    value !== null &&
    "id" in value &&
    typeof value.id === "string" &&
    "stages" in value &&
    Array.isArray(value.stages)
  );
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

export function useDeleteInterviewProcess() {
  return useJournalMutation((id: string) => api.deleteInterviewProcess(id));
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

export function useUpdateInterviewStage() {
  return useJournalMutation(
    ({
      processId,
      stageId,
      payload,
    }: {
      processId: string;
      stageId: string;
      payload: InterviewProcessStageMutation;
    }) => api.updateInterviewProcessStage(processId, stageId, payload),
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
      onStatus,
      signal,
    }: {
      processId: string;
      stageId: string;
      file: File;
      onProgress?: UploadOptions["onProgress"];
      onStatus?: UploadOptions["onStatus"];
      signal?: AbortSignal;
    }) =>
      api.uploadInterviewStageMedia(processId, stageId, file, {
        onProgress,
        onStatus,
        signal,
      }),
  );
}

export function useDeleteInterviewStageMedia() {
  return useJournalMutation(
    ({ processId, stageId }: { processId: string; stageId: string }) =>
      api.deleteInterviewStageMedia(processId, stageId),
  );
}

export function useUploadInterviewStageAttachments() {
  return useJournalMutation(
    async ({
      processId,
      stageId,
      files,
      options,
      onFileComplete,
      onFileStart,
    }: {
      processId: string;
      stageId: string;
      files: File[];
      options?: UploadOptions;
      onFileComplete?: (file: File) => void;
      onFileStart?: (file: File, index: number, total: number) => void;
    }) => {
      const totalBytes = files.reduce((total, file) => total + file.size, 0);
      let completedBytes = 0;
      let result = null;
      for (const [index, file] of files.entries()) {
        onFileStart?.(file, index, files.length);
        result = await api.uploadInterviewStageAttachment(
          processId,
          stageId,
          file,
          {
            signal: options?.signal,
            onProgress: (percent) => {
              const overallPercent =
                totalBytes > 0
                  ? Math.round(
                      ((completedBytes + (file.size * percent) / 100) /
                        totalBytes) *
                        100,
                    )
                  : 0;
              options?.onProgress?.(overallPercent);
            },
            onStatus: (status) => {
              const uploadedBytes = Math.min(
                totalBytes,
                completedBytes + status.uploadedBytes,
              );
              options?.onStatus?.({
                ...status,
                percent:
                  totalBytes > 0
                    ? Math.round((uploadedBytes / totalBytes) * 100)
                    : 0,
                uploadedBytes,
                totalBytes,
                etaSeconds:
                  status.bytesPerSecond && status.bytesPerSecond > 0
                    ? Math.max(
                        0,
                        (totalBytes - uploadedBytes) / status.bytesPerSecond,
                      )
                    : null,
              });
            },
          },
        );
        onFileComplete?.(file);
        completedBytes += file.size;
      }
      return result ?? api.interviewProcess(processId);
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
    async ({
      processId,
      file,
      options,
    }: {
      processId: string;
      file?: File | null;
      options?: UploadOptions;
    }) => {
      await api.setInterviewProcessOutcome(processId, { status: "offer" });
      if (file) {
        try {
          return await api.uploadInterviewOffer(processId, file, options);
        } catch (error) {
          const reason = error instanceof Error ? ` ${error.message}` : "";
          const message = `Оффер отмечен, но файл не загрузился.${reason} Повторите загрузку файла в открывшемся блоке оффера.`;
          if (error instanceof ApiError) {
            throw new ApiError(error.status, error.code, message);
          }
          throw new Error(message, { cause: error });
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
