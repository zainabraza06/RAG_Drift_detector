/**
 * Keeping a sleeping backend out of the user's way.
 *
 * On a free host (Render) the API sleeps after 15 idle minutes and takes a
 * minute or more to wake. This pings it the moment the app loads, so the wake
 * starts while the user is still reading the page rather than when they click
 * "Run evaluation", and keeps pinging while the tab is open so it never falls
 * asleep mid-session.
 */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { api } from "./api";

/** Under Render's 15-minute idle cutoff, with margin for a throttled tab. */
export const KEEPALIVE_MS = 10 * 60_000;
/** A warm API answers well inside this; past it, it is waking up. */
export const WAKING_AFTER_MS = 2_500;
const RETRY_DELAY_MS = 3_000;
/** About three minutes of retries: longer than any cold start we have seen. */
const MAX_RETRIES = 60;

export type BackendState = "checking" | "waking" | "ready" | "unreachable";

export const backendKey = ["backend-awake"] as const;

/**
 * Every caller shares one query, so the shell, the banner and the button see
 * the same state and trigger one ping between them.
 */
export function useBackendState(): BackendState {
  const query = useQuery({
    queryKey: backendKey,
    queryFn: api.ping,
    retry: MAX_RETRIES,
    retryDelay: RETRY_DELAY_MS,
    staleTime: KEEPALIVE_MS,
    refetchInterval: KEEPALIVE_MS,
  });

  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!query.isPending) return;
    const timer = setTimeout(() => setSlow(true), WAKING_AFTER_MS);
    return () => clearTimeout(timer);
  }, [query.isPending]);

  if (query.isSuccess) return "ready";
  if (query.isError) return "unreachable";
  return slow ? "waking" : "checking";
}

/**
 * Once a waking backend answers, refetch whatever failed while it slept, so
 * the page recovers by itself instead of stranding the user on an error.
 */
export function useRecoverAfterWake(state: BackendState): void {
  const client = useQueryClient();
  const woke = useRef(false);

  useEffect(() => {
    if (state === "waking") woke.current = true;
    if (state === "ready" && woke.current) {
      woke.current = false;
      void client.refetchQueries({
        predicate: (query) => query.state.status === "error",
      });
    }
  }, [state, client]);
}
