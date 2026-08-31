import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  ConsultationStatus,
  ConsultationType,
  PythonRepeatApplicationStatus,
} from "../../types/api";

export const opportunityKeys = {
  all: ["opportunities"] as const,
  mine: ["opportunities", "me"] as const,
  admin: ["opportunities", "admin"] as const,
  pythonRepeat: ["opportunities", "python-repeat"] as const,
  adminPythonRepeat: ["opportunities", "admin", "python-repeat"] as const,
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

export function usePythonRepeat() {
  return useQuery({
    queryKey: opportunityKeys.pythonRepeat,
    queryFn: api.myPythonRepeat,
  });
}

function usePythonRepeatMutation<T>(
  mutationFn: (payload: T) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (data) => {
      queryClient.setQueryData(opportunityKeys.pythonRepeat, data);
      void queryClient.invalidateQueries({ queryKey: opportunityKeys.all });
    },
  });
}

export function useCreatePythonRepeatApplication() {
  return usePythonRepeatMutation(api.createPythonRepeatApplication);
}

export function useUpdatePythonRepeatApplication() {
  return usePythonRepeatMutation(
    ({ id, payload }: { id: string; payload: Record<string, unknown> }) =>
      api.updatePythonRepeatApplication(id, payload),
  );
}

export function useSubmitPythonRepeatApplication() {
  return usePythonRepeatMutation(api.submitPythonRepeatApplication);
}

export function useAcceptPythonRepeatTerms() {
  return usePythonRepeatMutation(api.acceptPythonRepeatTerms);
}

export function useCheckoutPythonRepeat() {
  return useMutation({ mutationFn: api.checkoutPythonRepeat });
}

export function useCreatePythonRepeatOffer() {
  return usePythonRepeatMutation(api.createPythonRepeatOffer);
}

export function useSubmitPythonRepeatOffer() {
  return usePythonRepeatMutation(api.submitPythonRepeatOffer);
}

export function useCheckoutPythonRepeatInstallment() {
  return useMutation({ mutationFn: api.checkoutPythonRepeatInstallment });
}

export function useCompleteDevelopmentPythonRepeatPayment() {
  return usePythonRepeatMutation(api.completeDevelopmentPythonRepeatPayment);
}

export function useAdminPythonRepeat() {
  return useQuery({
    queryKey: opportunityKeys.adminPythonRepeat,
    queryFn: api.adminPythonRepeat,
  });
}

function useAdminPythonRepeatMutation<T>(
  mutationFn: (payload: T) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: (data) => {
      queryClient.setQueryData(opportunityKeys.adminPythonRepeat, data);
      void queryClient.invalidateQueries({ queryKey: opportunityKeys.all });
    },
  });
}

export function useTransitionAdminPythonRepeat() {
  return useAdminPythonRepeatMutation(
    (payload: {
      id: string;
      status: PythonRepeatApplicationStatus;
      comment: string;
      responsible_user_id: string | null;
    }) =>
      api.transitionAdminPythonRepeat(payload.id, {
        status: payload.status,
        comment: payload.comment,
        responsible_user_id: payload.responsible_user_id,
      }),
  );
}

export function useOverrideAdminPythonRepeatEligibility() {
  return useAdminPythonRepeatMutation(
    (payload: { id: string; reason: string }) =>
      api.overrideAdminPythonRepeatEligibility(payload.id, payload.reason),
  );
}

export function useAssignAdminPythonRepeatMentor() {
  return useAdminPythonRepeatMutation(
    (payload: { enrollmentId: string; mentorId: string }) =>
      api.assignAdminPythonRepeatMentor(payload.enrollmentId, payload.mentorId),
  );
}

export function useDecideAdminPythonRepeatOffer() {
  return useAdminPythonRepeatMutation(
    (payload: {
      offerId: string;
      verified: boolean;
      salary_base_kopecks: number | null;
      comment: string;
    }) =>
      api.decideAdminPythonRepeatOffer(payload.offerId, {
        verified: payload.verified,
        salary_base_kopecks: payload.salary_base_kopecks,
        comment: payload.comment,
      }),
  );
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
