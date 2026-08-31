import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { ConsultationStatus, ConsultationType } from "../../types/api";

export const opportunityKeys = {
  all: ["opportunities"] as const,
  mine: ["opportunities", "me"] as const,
  admin: ["opportunities", "admin"] as const,
};

function useMineMutation<T>(mutationFn: (payload: T) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (dashboard) => {
      queryClient.setQueryData(opportunityKeys.mine, dashboard);
      void queryClient.invalidateQueries({ queryKey: opportunityKeys.all });
    },
  });
}

export function useMyOpportunities() {
  return useQuery({
    queryKey: opportunityKeys.mine,
    queryFn: api.myOpportunities,
  });
}

export function useCreateConsultation() {
  return useMineMutation(api.createConsultation);
}

export function useCreateConsultationPaymentLink() {
  return useMutation({ mutationFn: api.createConsultationPaymentLink });
}

export function useCreateGoTransition() {
  return useMineMutation(api.createGoTransition);
}

export function useAcceptGoTransition() {
  return useMineMutation(api.acceptGoTransition);
}

export function useCreateGoTransitionPaymentLink() {
  return useMutation({ mutationFn: api.createGoTransitionPaymentLink });
}

export function useCompleteDevelopmentOpportunityPayment() {
  return useMineMutation(api.completeDevelopmentOpportunityPayment);
}

export function useAdminOpportunities() {
  return useQuery({
    queryKey: opportunityKeys.admin,
    queryFn: api.adminOpportunities,
  });
}

export function useUpdateAdminConsultation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      status,
      mentor_id,
      scheduled_at,
      admin_note,
      written_summary,
    }: {
      id: string;
      status: ConsultationStatus;
      mentor_id: string | null;
      scheduled_at: string | null;
      admin_note: string | null;
      written_summary: string | null;
    }) =>
      api.updateAdminConsultation(id, {
        status,
        mentor_id,
        scheduled_at,
        admin_note,
        written_summary,
      }),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(opportunityKeys.admin, dashboard);
      void queryClient.invalidateQueries({ queryKey: opportunityKeys.all });
    },
  });
}

export function useSetAdminConsultationMentor() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      mentorId,
      enabled,
    }: {
      mentorId: string;
      enabled: boolean;
    }) => api.setAdminConsultationMentor(mentorId, enabled),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(opportunityKeys.admin, dashboard);
      void queryClient.invalidateQueries({ queryKey: opportunityKeys.mine });
    },
  });
}

export function useUpdateAdminConsultationType() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      consultationType,
      priceKopecks,
      comparisonPriceKopecks,
      mentorRewardKopecks,
      durationMinutes,
    }: {
      consultationType: ConsultationType;
      priceKopecks: number;
      comparisonPriceKopecks: number;
      mentorRewardKopecks: number;
      durationMinutes: number;
    }) =>
      api.updateAdminConsultationType(consultationType, {
        price_kopecks: priceKopecks,
        comparison_price_kopecks: comparisonPriceKopecks,
        mentor_reward_kopecks: mentorRewardKopecks,
        duration_minutes: durationMinutes,
      }),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(opportunityKeys.admin, dashboard);
      void queryClient.invalidateQueries({ queryKey: opportunityKeys.mine });
    },
  });
}

export function useUpdateAdminGoTransitionProgram() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.updateAdminGoTransitionProgram,
    onSuccess: (dashboard) => {
      queryClient.setQueryData(opportunityKeys.admin, dashboard);
      void queryClient.invalidateQueries({ queryKey: opportunityKeys.mine });
    },
  });
}

export function useDecideAdminGoTransition() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      approved,
      admin_note,
    }: {
      id: string;
      approved: boolean;
      admin_note: string | null;
    }) => api.decideAdminGoTransition(id, { approved, admin_note }),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(opportunityKeys.admin, dashboard);
      void queryClient.invalidateQueries({ queryKey: opportunityKeys.all });
    },
  });
}
