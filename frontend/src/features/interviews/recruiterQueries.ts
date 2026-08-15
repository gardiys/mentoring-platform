import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  RecruiterContactPage,
  RecruiterFeedbackMutation,
  RecruiterSort,
} from "../../types/api";

export const recruiterKeys = {
  all: ["interviews", "recruiters"] as const,
  list: (
    query: string,
    trackId: string | null,
    contacted: boolean | null,
    sort: RecruiterSort,
    page: number,
  ) => [...recruiterKeys.all, query, trackId, contacted, sort, page] as const,
};

export function useRecruiters(
  query: string,
  trackId: string | null,
  contacted: boolean | null,
  sort: RecruiterSort,
  page: number,
) {
  return useQuery({
    queryKey: recruiterKeys.list(query, trackId, contacted, sort, page),
    queryFn: () =>
      api.interviewRecruiters(
        { query, trackId, contacted, sort },
        { limit: 24, offset: (page - 1) * 24 },
      ),
  });
}

export function useOpenRecruiterContact() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.openRecruiterContact,
    onSuccess: async (result) => {
      queryClient.setQueriesData<RecruiterContactPage>(
        { queryKey: recruiterKeys.all },
        (page) =>
          page
            ? {
                ...page,
                items: page.items.map((group) => ({
                  ...group,
                  recruiters: group.recruiters.map((recruiter) =>
                    recruiter.id === result.recruiter_id
                      ? {
                          ...recruiter,
                          total_contact_opens: result.total_contact_opens,
                          students_contacted_count:
                            result.students_contacted_count,
                          last_contacted_at: result.last_contacted_at,
                          has_contacted: true,
                          my_contact_opens: result.my_contact_opens,
                          my_last_contacted_at: result.my_last_contacted_at,
                        }
                      : recruiter,
                  ),
                })),
              }
            : page,
      );
      await queryClient.invalidateQueries({
        queryKey: recruiterKeys.all,
        refetchType: "none",
      });
    },
  });
}

export function useSetRecruiterFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      recruiterId,
      payload,
    }: {
      recruiterId: string;
      payload: RecruiterFeedbackMutation;
    }) => api.setRecruiterFeedback(recruiterId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: recruiterKeys.all });
    },
  });
}

export function useDeleteRecruiterFeedback() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.deleteRecruiterFeedback,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: recruiterKeys.all });
    },
  });
}
