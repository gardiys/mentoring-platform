import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { EmploymentProfileClassification } from "../../types/api";

export const employmentKeys = {
  all: ["employment-cases"] as const,
  mine: ["employment-cases", "me"] as const,
  tracks: ["employment-cases", "me", "tracks"] as const,
  student: (studentId: string) =>
    ["employment-cases", "student", studentId] as const,
};

export function useMyEmploymentCases() {
  return useQuery({
    queryKey: employmentKeys.mine,
    queryFn: api.myEmploymentCases,
  });
}

export function useMyEmploymentTrackOptions() {
  return useQuery({
    queryKey: employmentKeys.tracks,
    queryFn: api.myEmploymentTrackOptions,
  });
}

export function useReportEmploymentOffer() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: api.reportEmploymentOffer,
    onSuccess: () => client.invalidateQueries({ queryKey: employmentKeys.all }),
  });
}

function studentCaseMutation(
  mutationFn: (variables: {
    caseId: string;
    payload: Record<string, unknown>;
  }) => Promise<unknown>,
) {
  return function useCaseMutation() {
    const client = useQueryClient();
    return useMutation({
      mutationFn,
      onSuccess: () =>
        client.invalidateQueries({ queryKey: employmentKeys.all }),
    });
  };
}

export const useReportEmploymentWorkStart = studentCaseMutation(
  ({ caseId, payload }) => api.reportEmploymentWorkStart(caseId, payload),
);
export const useReportEmploymentOfferStatus = studentCaseMutation(
  ({ caseId, payload }) => api.reportEmploymentOfferStatus(caseId, payload),
);
export const useReportEmploymentActualDuties = studentCaseMutation(
  ({ caseId, payload }) => api.reportEmploymentActualDuties(caseId, payload),
);
export const useReportEmploymentChange = studentCaseMutation(
  ({ caseId, payload }) => api.reportEmploymentChange(caseId, payload),
);
export const useReportEmploymentEnd = studentCaseMutation(
  ({ caseId, payload }) => api.reportEmploymentEnd(caseId, payload),
);
export const useOpenEmploymentDispute = studentCaseMutation(
  ({ caseId, payload }) => api.openEmploymentDispute(caseId, payload),
);

export function useStudentEmploymentCases(studentId: string) {
  return useQuery({
    queryKey: employmentKeys.student(studentId),
    queryFn: () => api.employmentCasesForStudent(studentId),
    enabled: Boolean(studentId),
  });
}

export function useAssessEmploymentCase(studentId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      caseId,
      classification,
      startedAt,
      rationale,
      criterion,
      lockVersion,
    }: {
      caseId: string;
      classification: EmploymentProfileClassification;
      startedAt: string | null;
      rationale: string;
      criterion: string | null;
      lockVersion: number;
    }) =>
      api.assessEmploymentCase(studentId, caseId, {
        classification,
        effective_profile_started_at: startedAt,
        rationale,
        qualifying_criteria: criterion ? [{ criterion }] : [],
        non_qualifying_reasons:
          classification === "non_profile" ? [rationale] : [],
        evidence_ids: [],
        expected_lock_version: lockVersion,
        idempotency_key: crypto.randomUUID(),
      }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: employmentKeys.student(studentId) }),
  });
}

export function useRequestEmploymentInformation(studentId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      caseId,
      fields,
      dueAt,
    }: {
      caseId: string;
      fields: string[];
      dueAt: string;
    }) =>
      api.requestEmploymentInformation(studentId, caseId, {
        requested_fields: fields,
        due_at: dueAt,
        idempotency_key: crypto.randomUUID(),
      }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: employmentKeys.student(studentId) }),
  });
}

export function useRequestEmploymentAISuggestion(studentId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      caseId,
      evidenceIds,
    }: {
      caseId: string;
      evidenceIds: string[];
    }) =>
      api.requestEmploymentAISuggestion(studentId, caseId, {
        evidence_ids: evidenceIds,
        idempotency_key: crypto.randomUUID(),
      }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: employmentKeys.student(studentId) }),
  });
}

export function useResolveEmploymentDispute(studentId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      caseId,
      disputeId,
      resolution,
      outcome,
    }: {
      caseId: string;
      disputeId: string;
      resolution: string;
      outcome: "resolved" | "rejected";
    }) =>
      api.resolveEmploymentDispute(studentId, caseId, disputeId, {
        resolution,
        outcome,
      }),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: employmentKeys.student(studentId) }),
  });
}

export function useUploadEmploymentEvidence() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      caseId,
      evidenceType,
      file,
      onProgress,
    }: {
      caseId: string;
      evidenceType: string;
      file: File;
      onProgress?: (value: number) => void;
    }) =>
      api.uploadEmploymentEvidence(caseId, evidenceType, file, {
        onProgress,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: employmentKeys.all }),
  });
}
