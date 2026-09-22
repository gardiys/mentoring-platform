import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { api } from "../../api/endpoints";
import { filtersFromParams } from "./filters";
import { cardAutomationKeys, type CardAutomationScope } from "./queries";

type ReviewSession = { ids: string[]; completed: string[] };

export function adjacentReviewId(
  session: ReviewSession,
  currentId: string,
  direction = 1,
) {
  const current = session.ids.indexOf(currentId);
  for (let step = 1; step <= session.ids.length; step++) {
    const index =
      (current + direction * step + session.ids.length) % session.ids.length;
    const id = session.ids[index];
    if (id && id !== currentId && !session.completed.includes(id)) return id;
  }
  return null;
}

export function useReviewQueue(scope: CardAutomationScope, currentId: string) {
  const location = useLocation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const refreshedMissingId = useRef<string | null>(null);
  const mounted = useRef(false);
  const activeId = useRef(currentId);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    activeId.current = currentId;
  }, [currentId]);
  const filters = useMemo(() => {
    const parsed = filtersFromParams(new URLSearchParams(location.search));
    return {
      ...parsed,
      directionId: scope === "admin" ? parsed.directionId : null,
    };
  }, [location.search, scope]);
  // A session is a fixed snapshot, not a paginated list whose offsets shift after each decision.
  const key = [
    ...cardAutomationKeys.scope(scope),
    "review-session",
    filters,
  ] as const;
  const query = useQuery({
    queryKey: key,
    queryFn: async (): Promise<ReviewSession> => ({
      ids: await api.cardAutomationReviewQueue(scope, filters),
      completed: [],
    }),
    staleTime: Infinity,
    gcTime: 30 * 60 * 1000,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const nextId = query.data ? adjacentReviewId(query.data, currentId) : null;
  const previousId = query.data
    ? adjacentReviewId(query.data, currentId, -1)
    : null;
  const { data: session, isFetching, isError, refetch } = query;
  useEffect(() => {
    // Returning from the list may open a newly arrived card outside the cached session.
    // Refresh once, without repeatedly fetching for a direct link to a closed card.
    if (
      session &&
      !isFetching &&
      !isError &&
      !session.ids.includes(currentId) &&
      refreshedMissingId.current !== currentId
    ) {
      refreshedMissingId.current = currentId;
      void refetch();
    }
  }, [currentId, session, isFetching, isError, refetch]);
  const go = (id: string | null) => {
    if (id && mounted.current && activeId.current === currentId)
      void navigate({
        pathname: `/${scope}/card-automation/clusters/${id}`,
        search: location.search,
      });
  };
  const complete = (id: string) => {
    const session = client.getQueryData<ReviewSession>(key);
    if (!session) return;
    const updated = {
      ...session,
      completed: session.ids.includes(id)
        ? [...new Set([...session.completed, id])]
        : session.completed,
    };
    client.setQueryData(key, updated);
    go(adjacentReviewId(updated, id));
  };
  useEffect(() => {
    if (!nextId) return;
    void client.prefetchQuery({
      queryKey: cardAutomationKeys.cluster(scope, nextId),
      queryFn: () =>
        scope === "admin"
          ? api.adminCardAutomationCluster(nextId)
          : api.mentorCardAutomationCluster(nextId),
      staleTime: 30_000,
    });
  }, [client, scope, nextId]);
  return {
    busy,
    isManualReview: filters.needsActionOnly,
    setBusy,
    query,
    nextId,
    previousId,
    total: query.data?.ids.length ?? 0,
    completed: query.data?.completed.length ?? 0,
    containsCurrent: query.data?.ids.includes(currentId) ?? false,
    currentCompleted: query.data?.completed.includes(currentId) ?? false,
    next: () => go(nextId),
    previous: () => go(previousId),
    complete,
    refresh: async () => {
      const result = await query.refetch();
      if (result.isSuccess) go(result.data.ids[0] ?? null);
    },
  };
}

export type ReviewQueue = ReturnType<typeof useReviewQueue>;
