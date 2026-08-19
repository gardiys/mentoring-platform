import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { OnboardingApplicationAction } from "../../types/api";

export interface AdminApplicationListOptions {
  query: string;
  statuses: string[];
  page: number;
  pageSize: number;
}

export const adminApplicationKeys = {
  all: ["admin", "applications"] as const,
  list: (options: AdminApplicationListOptions) =>
    ["admin", "applications", "list", options] as const,
  detail: (applicantId: string) =>
    ["admin", "applications", applicantId] as const,
};

export function useAdminApplications(options: AdminApplicationListOptions) {
  return useQuery({
    queryKey: adminApplicationKeys.list(options),
    queryFn: () =>
      api.adminApplications({
        query: options.query,
        statuses: options.statuses,
        limit: options.pageSize,
        offset: (options.page - 1) * options.pageSize,
      }),
    placeholderData: (previousData) => previousData,
  });
}

export function useAdminApplication(applicantId: string | null) {
  return useQuery({
    queryKey: adminApplicationKeys.detail(applicantId ?? ""),
    queryFn: () => api.adminApplication(applicantId ?? ""),
    enabled: Boolean(applicantId),
  });
}

export function useExecuteAdminApplicationAction() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      applicantId,
      action,
      comment,
    }: {
      applicantId: string;
      action: OnboardingApplicationAction;
      comment?: string | null;
    }) => api.executeAdminApplicationAction(applicantId, action, comment),
    onSuccess: async (result) => {
      queryClient.setQueryData(
        adminApplicationKeys.detail(result.application.applicant_id),
        result.application,
      );
      await queryClient.invalidateQueries({
        queryKey: adminApplicationKeys.all,
      });
    },
  });
}
