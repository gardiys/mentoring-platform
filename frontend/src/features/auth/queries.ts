import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";

export const meQueryKey = ["me"] as const;

export function useMe(enabled = true) {
  return useQuery({
    queryKey: meQueryKey,
    queryFn: api.me,
    retry: false,
    enabled,
  });
}

export function useCompleteOnboarding() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: api.completeOnboarding,
    onSuccess: (user) => queryClient.setQueryData(meQueryKey, user),
  });
}
