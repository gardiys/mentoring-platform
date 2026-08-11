import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/endpoints";
import type {
  AdminCompanyAliasProposalMutation,
  CompanyAliasProposalStatus,
} from "../../types/api";

export const companyAliasKeys = {
  all: ["admin", "company-alias-proposals"] as const,
  list: (status: string, query: string, offset: number) =>
    [...companyAliasKeys.all, status, query, offset] as const,
};

export function useAdminCompanyAliasProposals(
  status: CompanyAliasProposalStatus | "all",
  query: string,
  offset: number,
) {
  return useQuery({
    queryKey: companyAliasKeys.list(status, query, offset),
    queryFn: () =>
      api.adminCompanyAliasProposals({
        status,
        q: query || undefined,
        limit: 20,
        offset,
      }),
  });
}

export function useModerateCompanyAliasProposal() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      proposalId,
      payload,
    }: {
      proposalId: string;
      payload: AdminCompanyAliasProposalMutation;
    }) => api.moderateCompanyAliasProposal(proposalId, payload),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: companyAliasKeys.all }),
  });
}
