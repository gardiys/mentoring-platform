import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { AdminMentorMutation } from "../../types/api";
import { adminStudentKeys } from "./studentQueries";

export const adminMentorKeys = {
  all: ["admin", "mentors"] as const,
  candidates: (query: string) =>
    ["admin", "mentors", "candidates", query] as const,
};

export function useAdminMentors() {
  return useQuery({ queryKey: adminMentorKeys.all, queryFn: api.adminMentors });
}

export function useAdminMentorCandidates(query: string) {
  return useQuery({
    queryKey: adminMentorKeys.candidates(query),
    queryFn: () => api.adminMentorCandidates(query),
  });
}

function useMentorMutation<T>(mutationFn: (value: T) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: adminMentorKeys.all }),
        queryClient.invalidateQueries({ queryKey: adminStudentKeys.all }),
        queryClient.invalidateQueries({ queryKey: adminStudentKeys.options }),
        queryClient.invalidateQueries({ queryKey: ["mentor"] }),
      ]);
    },
  });
}

export function useCreateAdminMentor() {
  return useMentorMutation((payload: AdminMentorMutation) =>
    api.createAdminMentor(payload),
  );
}

export function usePromoteAdminStudent() {
  return useMentorMutation((studentId: string) =>
    api.promoteAdminStudent(studentId),
  );
}

export function useRemoveAdminMentor() {
  return useMentorMutation((mentorId: string) =>
    api.removeAdminMentor(mentorId),
  );
}

export function useUpdateAdminMentorDirections() {
  return useMentorMutation(
    ({ mentorId, trackIds }: { mentorId: string; trackIds: string[] }) =>
      api.updateAdminMentorDirections(mentorId, trackIds),
  );
}

export function useReassignAdminMentorStudent() {
  return useMentorMutation(
    ({ studentId, mentorId }: { studentId: string; mentorId: string }) =>
      api.reassignAdminMentorStudent(studentId, mentorId),
  );
}
