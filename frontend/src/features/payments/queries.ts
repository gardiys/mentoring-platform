import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  AdminEmploymentPaymentStatus,
  EmploymentMutation,
  PaymentInstallmentStatus,
} from "../../types/api";
import type { UploadOptions } from "../../api/client";

export const paymentKeys = {
  all: ["payments"] as const,
  mine: ["payments", "me"] as const,
  student: (studentId: string) => ["payments", "student", studentId] as const,
  admin: (status: PaymentInstallmentStatus | null, page: number) =>
    ["payments", "admin", status, page] as const,
  adminStudents: (status: AdminEmploymentPaymentStatus, page: number) =>
    ["payments", "admin", "students", status, page] as const,
  adminStudent: (studentId: string) =>
    ["payments", "admin", "student", studentId] as const,
  overdue: (page: number) => ["payments", "admin", "overdue", page] as const,
  rewards: ["payments", "mentor", "rewards"] as const,
  mentorPayouts: ["payments", "admin", "mentor-payouts"] as const,
  mentorPayoutDetail: (mentorId: string) =>
    ["payments", "admin", "mentor-payouts", mentorId] as const,
};

export function useMyPayments() {
  return useQuery({ queryKey: paymentKeys.mine, queryFn: api.myPayments });
}

export function useUpdateMyPaymentDays() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.updateMyPaymentDays,
    onSuccess: (dashboard) => {
      queryClient.setQueryData(paymentKeys.mine, dashboard);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useCreatePaymentLink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.createPaymentLink,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: paymentKeys.mine }),
  });
}

export function useStudentPayments(studentId: string) {
  return useQuery({
    queryKey: paymentKeys.student(studentId),
    queryFn: () => api.mentorStudentPayments(studentId),
    enabled: Boolean(studentId),
  });
}

export function useSetStudentEmployment(studentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: EmploymentMutation) =>
      api.setMentorStudentEmployment(studentId, payload),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(paymentKeys.student(studentId), dashboard);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useTerminateStudentEmployment(studentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: { ended_at: string; reason: string | null }) =>
      api.terminateMentorStudentEmployment(studentId, payload),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(paymentKeys.student(studentId), dashboard);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useUpdateStudentPaymentDays(studentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (days: number[]) => api.updateAdminPaymentDays(studentId, days),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(paymentKeys.student(studentId), dashboard);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useRescheduleAdminPayment(studentId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      installmentId,
      dueDate,
      reason,
    }: {
      installmentId: string;
      dueDate: string;
      reason: string;
    }) =>
      api.rescheduleAdminPayment(installmentId, {
        due_date: dueDate,
        reason,
      }),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(paymentKeys.adminStudent(studentId), dashboard);
      queryClient.setQueryData(paymentKeys.student(studentId), dashboard);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useAdminPayments(
  status: PaymentInstallmentStatus | null,
  page: number,
) {
  return useQuery({
    queryKey: paymentKeys.admin(status, page),
    queryFn: () =>
      api.adminPayments({ status, limit: 50, offset: (page - 1) * 50 }),
    placeholderData: (previous) => previous,
  });
}

export function useAdminPaymentStudents(
  status: AdminEmploymentPaymentStatus,
  page: number,
) {
  return useQuery({
    queryKey: paymentKeys.adminStudents(status, page),
    queryFn: () =>
      api.adminPaymentStudents({
        status,
        limit: 50,
        offset: (page - 1) * 50,
      }),
    placeholderData: (previous) => previous,
  });
}

export function useAdminPaymentStudent(studentId: string) {
  return useQuery({
    queryKey: paymentKeys.adminStudent(studentId),
    queryFn: () => api.adminPaymentStudent(studentId),
    enabled: Boolean(studentId),
  });
}

export function useAdminOverduePayments(page: number) {
  return useQuery({
    queryKey: paymentKeys.overdue(page),
    queryFn: () =>
      api.adminOverduePayments({ limit: 50, offset: (page - 1) * 50 }),
    placeholderData: (previous) => previous,
  });
}

export function useConfirmAdminPayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.confirmAdminPayment,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: paymentKeys.all }),
  });
}

export function useRevokeAdminPayment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      installmentId,
      reason,
    }: {
      installmentId: string;
      reason: string;
    }) => api.revokeAdminPayment(installmentId, reason),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: paymentKeys.all }),
  });
}

export function useMentorRewards() {
  return useQuery({
    queryKey: paymentKeys.rewards,
    queryFn: api.mentorRewards,
  });
}

export function useRequestMentorPayout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (amountRubles: number) => api.requestMentorPayout(amountRubles),
    onSuccess: (summary) => {
      queryClient.setQueryData(paymentKeys.rewards, summary);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useCancelMentorPayout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payoutId: string) => api.cancelMentorPayout(payoutId),
    onSuccess: (summary) => {
      queryClient.setQueryData(paymentKeys.rewards, summary);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useUploadMentorPayoutReceipt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      payoutId,
      file,
      options,
    }: {
      payoutId: string;
      file: File;
      options?: UploadOptions;
    }) => api.uploadMentorPayoutReceipt(payoutId, file, options),
    onSuccess: (summary) => {
      queryClient.setQueryData(paymentKeys.rewards, summary);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useDeleteMentorPayoutReceipt() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.deleteMentorPayoutReceipt,
    onSuccess: (summary) => {
      queryClient.setQueryData(paymentKeys.rewards, summary);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useAdminMentorPayouts() {
  return useQuery({
    queryKey: paymentKeys.mentorPayouts,
    queryFn: api.adminMentorPayouts,
  });
}

export function useAdminMentorPayoutDetail(mentorId: string) {
  return useQuery({
    queryKey: paymentKeys.mentorPayoutDetail(mentorId),
    queryFn: () => api.adminMentorPayoutDetail(mentorId),
    enabled: Boolean(mentorId),
  });
}

export function useCreateAdminMentorPayout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      mentorId,
      amountRubles,
      paymentReference,
    }: {
      mentorId: string;
      amountRubles: number;
      paymentReference: string | null;
    }) =>
      api.createAdminMentorPayout(mentorId, {
        amount_rubles: amountRubles,
        payment_reference: paymentReference,
      }),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(paymentKeys.mentorPayouts, dashboard);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useMarkAdminMentorPayoutPaid() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      payoutId,
      paymentReference,
    }: {
      payoutId: string;
      paymentReference: string | null;
    }) => api.markAdminMentorPayoutPaid(payoutId, paymentReference),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(paymentKeys.mentorPayouts, dashboard);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useCancelAdminMentorPayout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ payoutId, reason }: { payoutId: string; reason?: string }) =>
      api.cancelAdminMentorPayout(payoutId, reason ?? null),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(paymentKeys.mentorPayouts, dashboard);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useEditAdminMentorPayout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      payoutId,
      amountRubles,
      paymentReference,
      paidAt,
      reason,
    }: {
      payoutId: string;
      amountRubles: number;
      paymentReference: string | null;
      paidAt: string | null;
      reason: string;
    }) =>
      api.editAdminMentorPayout(payoutId, {
        amount_rubles: amountRubles,
        payment_reference: paymentReference,
        paid_at: paidAt,
        reason,
      }),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(paymentKeys.mentorPayouts, dashboard);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}

export function useMarkMentorRewardPaid() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.markAdminMentorRewardPaid,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: paymentKeys.all }),
  });
}

export function useVoidAdminMentorReward() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ rewardId, reason }: { rewardId: string; reason: string }) =>
      api.voidAdminMentorReward(rewardId, reason),
    onSuccess: (dashboard) => {
      queryClient.setQueryData(paymentKeys.mentorPayouts, dashboard);
      void queryClient.invalidateQueries({ queryKey: paymentKeys.all });
    },
  });
}
