import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";

export const notificationKeys = {
  all: ["notifications"] as const,
};

export function useNotifications() {
  return useQuery({
    queryKey: notificationKeys.all,
    queryFn: ({ signal }) => api.notifications(20, 0, signal),
    refetchInterval: 30_000,
    // A failed background refresh must not immediately create a second
    // request while the backend or connection is recovering. The next poll
    // or an explicit retry is enough, and already loaded notifications stay
    // visible in the cache.
    retry: false,
  });
}

export function useMarkNotificationRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.markNotificationRead,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  });
}

export function useMarkAllNotificationsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.markAllNotificationsRead,
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: notificationKeys.all }),
  });
}
