import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  AdminScheduleEventMutation,
  MentorOneOffActivityMutation,
  MentorWeeklyCallMutation,
  PinnedResourceLinkMutation,
  ScheduleEventKind,
} from "../../types/api";

export const scheduleKeys = {
  myMentor: ["my-mentor"] as const,
  mentorProfile: ["mentor", "profile"] as const,
  admin: ["admin", "schedule"] as const,
  adminList: (options: AdminScheduleListOptions) =>
    ["admin", "schedule", "list", options] as const,
  adminEvent: (eventId: string) =>
    ["admin", "schedule", "event", eventId] as const,
  usefulLinks: ["admin", "useful-links"] as const,
};

export interface AdminScheduleListOptions {
  trackId: string | null;
  kind: ScheduleEventKind | null;
  page: number;
}

export const ADMIN_SCHEDULE_PAGE_SIZE = 20;

export function useMyMentor() {
  return useQuery({
    queryKey: scheduleKeys.myMentor,
    queryFn: api.myMentorDashboard,
  });
}

export function useMentorProfile() {
  return useQuery({
    queryKey: scheduleKeys.mentorProfile,
    queryFn: api.mentorProfile,
  });
}

export function useUpdateMentorProfile() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: {
      consultation_url: string | null;
      group_calendar_url: string | null;
    }) => api.updateMentorProfile(payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.mentorProfile }),
        queryClient.invalidateQueries({ queryKey: scheduleKeys.myMentor }),
      ]);
    },
  });
}

function useWeeklyCallMutation(
  mutationFn: (variables: {
    eventId?: string;
    payload: MentorWeeklyCallMutation;
  }) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.mentorProfile }),
        queryClient.invalidateQueries({ queryKey: scheduleKeys.myMentor }),
      ]);
    },
  });
}

export function useSaveMentorWeeklyCall() {
  return useWeeklyCallMutation(({ eventId, payload }) =>
    eventId
      ? api.updateMentorWeeklyCall(eventId, payload)
      : api.createMentorWeeklyCall(payload),
  );
}

export function useDeleteMentorWeeklyCall() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.deleteMentorWeeklyCall,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.mentorProfile }),
        queryClient.invalidateQueries({ queryKey: scheduleKeys.myMentor }),
      ]);
    },
  });
}

function useOneOffActivityMutation(
  mutationFn: (variables: {
    eventId?: string;
    payload: MentorOneOffActivityMutation;
  }) => Promise<unknown>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.mentorProfile }),
        queryClient.invalidateQueries({ queryKey: scheduleKeys.myMentor }),
      ]);
    },
  });
}

export function useSaveMentorOneOffActivity() {
  return useOneOffActivityMutation(({ eventId, payload }) =>
    eventId
      ? api.updateMentorOneOffActivity(eventId, payload)
      : api.createMentorOneOffActivity(payload),
  );
}

export function useDeleteMentorOneOffActivity() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.deleteMentorOneOffActivity,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.mentorProfile }),
        queryClient.invalidateQueries({ queryKey: scheduleKeys.myMentor }),
      ]);
    },
  });
}

export function useRescheduleMentorWeeklyCall() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      eventId,
      startsAt,
    }: {
      eventId: string;
      startsAt: string;
    }) => api.rescheduleMentorWeeklyCall(eventId, { starts_at: startsAt }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.mentorProfile }),
        queryClient.invalidateQueries({ queryKey: scheduleKeys.myMentor }),
      ]);
    },
  });
}

export function useCancelMentorWeeklyCallReschedule() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.cancelMentorWeeklyCallReschedule,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.mentorProfile }),
        queryClient.invalidateQueries({ queryKey: scheduleKeys.myMentor }),
      ]);
    },
  });
}

export function useAdminSchedule(options: AdminScheduleListOptions) {
  return useQuery({
    queryKey: scheduleKeys.adminList(options),
    queryFn: () =>
      api.adminScheduleEvents({
        trackId: options.trackId,
        kind: options.kind,
        limit: ADMIN_SCHEDULE_PAGE_SIZE,
        offset: (options.page - 1) * ADMIN_SCHEDULE_PAGE_SIZE,
      }),
    placeholderData: (previous) => previous,
  });
}

export function useAdminScheduleEvent(eventId?: string) {
  return useQuery({
    queryKey: scheduleKeys.adminEvent(eventId ?? "new"),
    queryFn: () => api.adminScheduleEvent(eventId!),
    enabled: Boolean(eventId),
  });
}

export function useSaveAdminScheduleEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      eventId,
      payload,
    }: {
      eventId?: string;
      payload: AdminScheduleEventMutation;
    }) =>
      eventId
        ? api.updateAdminScheduleEvent(eventId, payload)
        : api.createAdminScheduleEvent(payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.admin }),
        queryClient.invalidateQueries({ queryKey: scheduleKeys.myMentor }),
      ]);
    },
  });
}

export function useDeleteAdminScheduleEvent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.deleteAdminScheduleEvent,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.admin }),
        queryClient.invalidateQueries({ queryKey: scheduleKeys.myMentor }),
      ]);
    },
  });
}

export function useAdminUsefulLinks() {
  return useQuery({
    queryKey: scheduleKeys.usefulLinks,
    queryFn: api.adminUsefulLinks,
  });
}

export function useSaveAdminUsefulLink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      linkId,
      payload,
    }: {
      linkId?: string;
      payload: PinnedResourceLinkMutation;
    }) =>
      linkId
        ? api.updateAdminUsefulLink(linkId, payload)
        : api.createAdminUsefulLink(payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.usefulLinks }),
        queryClient.invalidateQueries({ queryKey: scheduleKeys.myMentor }),
      ]);
    },
  });
}

export function useDeleteAdminUsefulLink() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.deleteAdminUsefulLink,
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: scheduleKeys.usefulLinks }),
        queryClient.invalidateQueries({ queryKey: scheduleKeys.myMentor }),
      ]);
    },
  });
}
