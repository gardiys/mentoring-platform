import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  AdminStudentMutation,
  StudentAccessFilter,
  StudentLearningStatus,
} from "../../types/api";
import { adminTrackKeys } from "./queries";

export interface AdminStudentListOptions {
  query: string;
  trackId: string | null;
  learningStatuses: StudentLearningStatus[];
  access: StudentAccessFilter;
  mentorFilter: string;
  page: number;
}

const PAGE_SIZE = 50;

export const adminStudentKeys = {
  all: ["admin", "students"] as const,
  list: (options: AdminStudentListOptions) =>
    ["admin", "students", "list", options] as const,
  detail: (id: string) => ["admin", "students", id] as const,
  options: ["admin", "students", "options"] as const,
};

export function useAdminStudents(options: AdminStudentListOptions) {
  return useQuery({
    queryKey: adminStudentKeys.list(options),
    queryFn: () =>
      api.adminStudents({
        query: options.query,
        trackId: options.trackId,
        learningStatuses: options.learningStatuses,
        isActive: options.access === "all" ? null : options.access === "active",
        mentorId:
          options.mentorFilter !== "all" &&
          options.mentorFilter !== "unassigned"
            ? options.mentorFilter
            : null,
        withoutMentor: options.mentorFilter === "unassigned",
        limit: PAGE_SIZE,
        offset: (options.page - 1) * PAGE_SIZE,
      }),
    placeholderData: (previousData) => previousData,
  });
}

export function useAdminStudent(id: string) {
  return useQuery({
    queryKey: adminStudentKeys.detail(id),
    queryFn: () => api.adminStudent(id),
    enabled: Boolean(id),
  });
}

export function useAdminStudentOptions() {
  return useQuery({
    queryKey: adminStudentKeys.options,
    queryFn: api.adminStudentOptions,
  });
}

async function invalidateStudentData(
  queryClient: ReturnType<typeof useQueryClient>,
) {
  await Promise.all([
    queryClient.invalidateQueries({ queryKey: adminStudentKeys.all }),
    queryClient.invalidateQueries({ queryKey: adminTrackKeys.all }),
    queryClient.invalidateQueries({ queryKey: ["mentor"] }),
    queryClient.invalidateQueries({ queryKey: ["roadmaps"] }),
  ]);
}

export function useCreateAdminStudent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: AdminStudentMutation) =>
      api.createAdminStudent(payload),
    onSuccess: async () => invalidateStudentData(queryClient),
  });
}

export function useUpdateAdminStudent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      payload,
    }: {
      id: string;
      payload: AdminStudentMutation;
    }) => api.updateAdminStudent(id, payload),
    onSuccess: async (student) => {
      queryClient.setQueryData(adminStudentKeys.detail(student.id), student);
      await invalidateStudentData(queryClient);
    },
  });
}

export function useSetAdminStudentAccess() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, isActive }: { id: string; isActive: boolean }) =>
      api.setAdminStudentAccess(id, isActive),
    onSuccess: async (student) => {
      queryClient.setQueryData(adminStudentKeys.detail(student.id), student);
      await invalidateStudentData(queryClient);
    },
  });
}

export function useSetAdminStudentPublicIdentity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      hidden,
      reason,
    }: {
      id: string;
      hidden: boolean;
      reason: string | null;
    }) => api.setAdminStudentPublicIdentity(id, hidden, reason),
    onSuccess: async (student) => {
      queryClient.setQueryData(adminStudentKeys.detail(student.id), student);
      await invalidateStudentData(queryClient);
    },
  });
}

export function useEraseAdminStudentPersonalData() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, reason }: { id: string; reason: string }) =>
      api.eraseAdminStudentPersonalData(id, reason),
    onSuccess: async (student) => {
      queryClient.setQueryData(adminStudentKeys.detail(student.id), student);
      await invalidateStudentData(queryClient);
    },
  });
}
