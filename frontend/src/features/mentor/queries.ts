import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type { UploadOptions } from "../../api/client";
import type {
  MentorAnalyticsPeriod,
  MentorDocumentKind,
  StudentAccessFilter,
  StudentLearningStatus,
  MentorStudentSort,
  StudentStrengthLevel,
} from "../../types/api";

export const mentorKeys = {
  all: ["mentor"] as const,
  students: ["mentor", "students"] as const,
  studentList: (options: MentorStudentListOptions) =>
    ["mentor", "students", "list", options] as const,
  interviewAnalytics: (options: MentorInterviewAnalyticsOptions) =>
    ["mentor", "students", "analytics", options] as const,
  student: (id: string) => ["mentor", "students", id] as const,
  interview: (studentId: string, processId: string) =>
    ["mentor", "students", studentId, "interviews", processId] as const,
  myMocks: ["mentor", "me", "mocks"] as const,
  myDocuments: ["mentor", "me", "documents"] as const,
};

export interface MentorStudentListOptions {
  query: string;
  trackId: string | null;
  mentorFilter: string;
  access: StudentAccessFilter;
  learningStatuses: StudentLearningStatus[];
  page: number;
  sort: MentorStudentSort;
}

export interface MentorInterviewAnalyticsOptions {
  period: MentorAnalyticsPeriod;
  trackId: string | null;
  mentorFilter: string;
  access: StudentAccessFilter;
  learningStatuses: StudentLearningStatus[];
}

const STUDENTS_PAGE_SIZE = 25;

export function useMentorStudents(options: MentorStudentListOptions) {
  return useQuery({
    queryKey: mentorKeys.studentList(options),
    queryFn: () =>
      api.mentorStudents({
        query: options.query,
        trackId: options.trackId,
        mentorId:
          options.mentorFilter !== "all" &&
          options.mentorFilter !== "unassigned"
            ? options.mentorFilter
            : null,
        withoutMentor: options.mentorFilter === "unassigned",
        isActive: options.access === "all" ? null : options.access === "active",
        learningStatuses: options.learningStatuses,
        sort: options.sort,
        limit: STUDENTS_PAGE_SIZE,
        offset: (options.page - 1) * STUDENTS_PAGE_SIZE,
      }),
    placeholderData: (previousData) => previousData,
  });
}

export function useMentorInterviewAnalytics(
  options: MentorInterviewAnalyticsOptions,
  enabled = true,
) {
  return useQuery({
    queryKey: mentorKeys.interviewAnalytics(options),
    queryFn: () =>
      api.mentorInterviewAnalytics({
        period: options.period,
        trackId: options.trackId,
        mentorId:
          options.mentorFilter !== "all" &&
          options.mentorFilter !== "unassigned"
            ? options.mentorFilter
            : null,
        withoutMentor: options.mentorFilter === "unassigned",
        isActive: options.access === "all" ? null : options.access === "active",
        learningStatuses: options.learningStatuses,
      }),
    enabled,
  });
}

export function useMentorStudent(id: string) {
  return useQuery({
    queryKey: mentorKeys.student(id),
    queryFn: () => api.mentorStudent(id),
    enabled: Boolean(id),
  });
}

function useStudentMutation<TVariables, TData>(
  studentId: string,
  mutationFn: (variables: TVariables) => Promise<TData>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: mentorKeys.students }),
        queryClient.invalidateQueries({
          queryKey: mentorKeys.student(studentId),
        }),
      ]);
    },
  });
}

export function useUpdateMentorStudentState(studentId: string) {
  return useStudentMutation(
    studentId,
    ({
      learningStatus,
      strengthLevel,
    }: {
      learningStatus: StudentLearningStatus;
      strengthLevel: StudentStrengthLevel | null;
    }) =>
      api.updateMentorStudentState(studentId, learningStatus, strengthLevel),
  );
}

export function useCreateMentorNote(studentId: string) {
  return useStudentMutation(studentId, (body: string) =>
    api.createMentorNote(studentId, body),
  );
}

export function useDeleteMentorNote(studentId: string) {
  return useStudentMutation(studentId, (noteId: string) =>
    api.deleteMentorNote(studentId, noteId),
  );
}

export function useSetMentorDocumentText(studentId: string) {
  return useStudentMutation(
    studentId,
    ({ kind, text }: { kind: MentorDocumentKind; text: string | null }) =>
      api.setMentorDocumentText(studentId, kind, text),
  );
}

export function useUploadMentorDocument(studentId: string) {
  return useStudentMutation(
    studentId,
    ({ kind, file }: { kind: MentorDocumentKind; file: File }) =>
      api.uploadMentorDocument(studentId, kind, file),
  );
}

export function useCreateMockInterview(studentId: string) {
  return useStudentMutation(
    studentId,
    (payload: { scheduled_at: string; description: string | null }) =>
      api.createMockInterview(studentId, payload),
  );
}

export function useCompleteMockInterview(studentId: string) {
  return useStudentMutation(
    studentId,
    ({ mockId, feedback }: { mockId: string; feedback: string }) =>
      api.completeMockInterview(studentId, mockId, feedback),
  );
}

export function useUploadMockInterviewMedia(studentId: string) {
  return useStudentMutation(
    studentId,
    ({
      mockId,
      file,
      onProgress,
      onStatus,
      signal,
    }: {
      mockId: string;
      file: File;
      onProgress?: (percent: number) => void;
      onStatus?: UploadOptions["onStatus"];
      signal?: AbortSignal;
    }) =>
      api.uploadMockInterviewMedia(studentId, mockId, file, {
        onProgress,
        onStatus,
        signal,
      }),
  );
}

export function useMentorInterview(studentId: string, processId: string) {
  return useQuery({
    queryKey: mentorKeys.interview(studentId, processId),
    queryFn: () => api.mentorInterview(studentId, processId),
    enabled: Boolean(studentId && processId),
  });
}

export function useCreateMentorInterviewFeedback(
  studentId: string,
  processId: string,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ stageId, body }: { stageId: string; body: string }) =>
      api.createMentorInterviewFeedback(studentId, stageId, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: mentorKeys.interview(studentId, processId),
      });
    },
  });
}

export function useMyMockInterviews(enabled = true) {
  return useQuery({
    queryKey: mentorKeys.myMocks,
    queryFn: api.myMockInterviews,
    enabled,
  });
}

export function useMyMentorDocuments(enabled = true) {
  return useQuery({
    queryKey: mentorKeys.myDocuments,
    queryFn: api.myMentorDocuments,
    enabled,
  });
}
