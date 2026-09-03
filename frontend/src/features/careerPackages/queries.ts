import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  CareerActiveSearchParameters,
  CareerSelfPresentationCard,
  CareerSourceData,
} from "../../types/api";

export const careerPackageKeys = {
  all: ["career-packages"] as const,
  student: (studentId: string) =>
    ["career-packages", "student", studentId] as const,
  options: (studentId: string) =>
    ["career-packages", "options", studentId] as const,
  me: ["career-packages", "me"] as const,
};

export function useStaffCareerPackages(studentId: string) {
  return useQuery({
    queryKey: careerPackageKeys.student(studentId),
    queryFn: () => api.careerPackagesForStudent(studentId),
    enabled: Boolean(studentId),
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === "generating")
        ? 3000
        : false,
  });
}

export function useCareerTrackOptions(studentId: string) {
  return useQuery({
    queryKey: careerPackageKeys.options(studentId),
    queryFn: () => api.careerPackageTrackOptions(studentId),
    enabled: Boolean(studentId),
  });
}

export function useMyCareerPackages() {
  return useQuery({
    queryKey: careerPackageKeys.me,
    queryFn: api.myCareerPackages,
  });
}

export function useCareerPackageActions(studentId: string) {
  const client = useQueryClient();
  const refreshStaff = () =>
    client.invalidateQueries({
      queryKey: careerPackageKeys.student(studentId),
    });
  return {
    create: useMutation({
      mutationFn: (trackId: string) =>
        api.createCareerPackage(studentId, trackId),
      onSuccess: refreshStaff,
    }),
    finalizeResume: useMutation({
      mutationFn: api.finalizeCareerResume,
      onSuccess: refreshStaff,
    }),
    saveDraft: useMutation({
      mutationFn: ({
        packageId,
        lockVersion,
        sourceData,
        selfPresentationCard,
        activeSearchParameters,
      }: {
        packageId: string;
        lockVersion: number;
        sourceData?: CareerSourceData;
        selfPresentationCard?: CareerSelfPresentationCard;
        activeSearchParameters?: CareerActiveSearchParameters;
      }) =>
        api.updateCareerDraft(packageId, {
          lock_version: lockVersion,
          source_data: sourceData,
          self_presentation_card: selfPresentationCard,
          active_search_parameters: activeSearchParameters,
        }),
      onSuccess: refreshStaff,
    }),
    generate: useMutation({
      mutationFn: (packageId: string) => api.generateCareerPackage(packageId),
      onSuccess: refreshStaff,
    }),
    validate: useMutation({
      mutationFn: api.validateCareerPackage,
      onSuccess: refreshStaff,
    }),
    publish: useMutation({
      mutationFn: api.publishCareerPackage,
      onSuccess: refreshStaff,
    }),
    recordObligation: useMutation({
      mutationFn: ({
        packageId,
        offerAcceptedOn,
        recordComment,
      }: {
        packageId: string;
        offerAcceptedOn: string;
        recordComment: string | null;
      }) =>
        api.recordCareerPackageObligation(packageId, {
          offer_accepted_on: offerAcceptedOn,
          record_comment: recordComment,
          eligibility_confirmed: true,
        }),
      onSuccess: refreshStaff,
    }),
    sendObligationNotice: useMutation({
      mutationFn: api.sendCareerPackageObligationNotice,
      onSuccess: refreshStaff,
    }),
    retryEmail: useMutation({
      mutationFn: api.retryCareerPackageEmail,
      onSuccess: refreshStaff,
    }),
    retryObligationEmail: useMutation({
      mutationFn: api.retryCareerPackageObligationEmail,
      onSuccess: refreshStaff,
    }),
    resolveObjection: useMutation({
      mutationFn: ({
        packageId,
        objectionId,
        status,
        resolutionComment,
        createRevision,
      }: {
        packageId: string;
        objectionId: string;
        status: "accepted" | "partially_accepted" | "rejected" | "resolved";
        resolutionComment: string;
        createRevision: boolean;
      }) =>
        api.resolveCareerObjection(packageId, objectionId, {
          status,
          resolution_comment: resolutionComment,
          create_revision: createRevision,
        }),
      onSuccess: refreshStaff,
    }),
    saveReview: useMutation({
      mutationFn: ({
        packageId,
        ...payload
      }: Parameters<typeof api.saveCareerReview>[1] & { packageId: string }) =>
        api.saveCareerReview(packageId, payload),
      onSuccess: refreshStaff,
    }),
  };
}
