import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  InterviewCatalogFilters,
  InterviewCatalogMediaKind,
  InterviewStageType,
} from "../../types/api";

const stageTypes = new Set<InterviewStageType>([
  "screening",
  "technical_screening",
  "technical_interview",
  "system_design",
  "final_interview",
  "other",
]);
const mediaKinds = new Set<InterviewCatalogMediaKind>([
  "any",
  "video",
  "audio",
]);

export function interviewCatalogFiltersFromParams(
  params: URLSearchParams,
): InterviewCatalogFilters {
  const stageType = params.get("stage_type") as InterviewStageType | null;
  const mediaKind = params.get(
    "media_kind",
  ) as InterviewCatalogMediaKind | null;
  return {
    query: params.get("q") ?? "",
    authorId: params.get("author_id"),
    trackId: params.get("track_id"),
    stageType: stageType && stageTypes.has(stageType) ? stageType : null,
    hasOffer: params.get("has_offer") === "true",
    mediaKind: mediaKind && mediaKinds.has(mediaKind) ? mediaKind : null,
    hasAiReview: params.get("has_ai_review") === "true",
  };
}

export const interviewCatalogKeys = {
  all: ["interviews", "catalog"] as const,
  directions: ["interviews", "catalog", "directions"] as const,
  authors: ["interviews", "catalog", "authors"] as const,
  companies: (filters: InterviewCatalogFilters, page: number) =>
    [
      "interviews",
      "catalog",
      "companies",
      filters.query,
      filters.authorId,
      filters.trackId,
      filters.stageType,
      filters.hasOffer,
      filters.mediaKind,
      filters.hasAiReview,
      page,
    ] as const,
  companyRoot: (companyId: string) =>
    ["interviews", "catalog", "company", companyId] as const,
  company: (companyId: string, filters: InterviewCatalogFilters) =>
    [
      ...interviewCatalogKeys.companyRoot(companyId),
      filters.authorId,
      filters.trackId,
      filters.stageType,
      filters.hasOffer,
      filters.mediaKind,
      filters.hasAiReview,
    ] as const,
};

export function useInterviewCatalogDirections() {
  return useQuery({
    queryKey: interviewCatalogKeys.directions,
    queryFn: api.interviewCatalogDirections,
    staleTime: 5 * 60_000,
  });
}

export function useInterviewCatalogAuthors() {
  return useQuery({
    queryKey: interviewCatalogKeys.authors,
    queryFn: api.interviewCatalogAuthors,
    staleTime: 5 * 60_000,
  });
}

export function useInterviewCatalogCompanies(
  filters: InterviewCatalogFilters,
  page: number,
) {
  return useQuery({
    queryKey: interviewCatalogKeys.companies(filters, page),
    queryFn: () =>
      api.interviewCatalogCompanies(filters, {
        limit: 24,
        offset: (page - 1) * 24,
      }),
  });
}

export function useInterviewCatalogCompany(
  companyId: string,
  filters: InterviewCatalogFilters,
) {
  return useQuery({
    queryKey: interviewCatalogKeys.company(companyId, filters),
    queryFn: () => api.interviewCatalogCompany(companyId, filters),
    enabled: Boolean(companyId),
  });
}

export function useCreateInterviewCatalogComment(companyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ stageId, body }: { stageId: string; body: string }) =>
      api.createInterviewCatalogComment(stageId, { body }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: interviewCatalogKeys.companyRoot(companyId),
      });
    },
  });
}

export function useDeleteInterviewCatalogComment(companyId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (commentId: string) =>
      api.deleteInterviewCatalogComment(commentId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: interviewCatalogKeys.companyRoot(companyId),
      });
    },
  });
}
