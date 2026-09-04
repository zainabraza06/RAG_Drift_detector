/**
 * TanStack Query hooks.
 *
 * Query keys are centralised so an invalidation can never miss a cache: a run
 * changes the dashboard, the trends, the drift feed and the run list at once,
 * and each of those has exactly one key prefix.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryResult,
} from "@tanstack/react-query";

import { api } from "./api";
import type {
  DashboardSummary,
  DiagnosticReport,
  DriftAssessment,
  DriftVerdict,
  GoldenSetInput,
  MetricSeries,
  Page,
  RunDetail,
  RunRecord,
  StoredGoldenSet,
  SystemInfo,
} from "./types";

export const keys = {
  dashboard: ["dashboard"] as const,
  system: ["system"] as const,
  runs: ["runs"] as const,
  run: (id: string) => ["runs", id] as const,
  runDetail: (id: string) => ["runs", id, "detail"] as const,
  runDrift: (id: string) => ["runs", id, "drift"] as const,
  runDiagnostics: (id: string) => ["runs", id, "diagnostics"] as const,
  trends: (k: number, limit: number) => ["trends", k, limit] as const,
  cutoffs: ["cutoffs"] as const,
  driftEvents: (verdict?: DriftVerdict) => ["drift-events", verdict ?? "all"] as const,
  goldenSets: ["golden-sets"] as const,
  goldenSet: (id: number) => ["golden-sets", id] as const,
};

export function useDashboard(): UseQueryResult<DashboardSummary> {
  return useQuery({ queryKey: keys.dashboard, queryFn: api.dashboard });
}

export function useSystemInfo(): UseQueryResult<SystemInfo> {
  return useQuery({ queryKey: keys.system, queryFn: api.systemInfo });
}

export function useRuns(limit = 25): UseQueryResult<Page<RunRecord>> {
  return useQuery({
    queryKey: [...keys.runs, limit],
    queryFn: () => api.listRuns({ limit }),
  });
}

export function useRunDetail(runId: string | undefined): UseQueryResult<RunDetail> {
  return useQuery({
    queryKey: keys.runDetail(runId ?? ""),
    queryFn: () => api.getRunDetail(runId as string),
    enabled: Boolean(runId),
  });
}

export function useRunDrift(
  runId: string | undefined,
): UseQueryResult<DriftAssessment> {
  return useQuery({
    queryKey: keys.runDrift(runId ?? ""),
    queryFn: () => api.runDrift(runId as string),
    enabled: Boolean(runId),
  });
}

export function useRunDiagnostics(
  runId: string | undefined,
): UseQueryResult<DiagnosticReport> {
  return useQuery({
    queryKey: keys.runDiagnostics(runId ?? ""),
    queryFn: () => api.runDiagnostics(runId as string),
    enabled: Boolean(runId),
    // A stable run has no diagnostics and returns 404; that is an expected
    // answer, not a failure worth retrying.
    retry: false,
  });
}

export function useTrends(k: number, limit = 50): UseQueryResult<MetricSeries[]> {
  return useQuery({
    queryKey: keys.trends(k, limit),
    queryFn: () => api.metricTrends({ k, limit }),
  });
}

export function useCutoffs(): UseQueryResult<number[]> {
  return useQuery({ queryKey: keys.cutoffs, queryFn: api.cutoffs });
}

export function useDriftEvents(
  verdict?: DriftVerdict,
): UseQueryResult<Page<DriftAssessment>> {
  return useQuery({
    queryKey: keys.driftEvents(verdict),
    queryFn: () => api.driftEvents({ limit: 50, verdict }),
  });
}

export function useGoldenSets(): UseQueryResult<Page<StoredGoldenSet>> {
  return useQuery({ queryKey: keys.goldenSets, queryFn: () => api.listGoldenSets() });
}

export function useGoldenSet(
  id: number | undefined,
): UseQueryResult<StoredGoldenSet> {
  return useQuery({
    queryKey: keys.goldenSet(id ?? 0),
    queryFn: () => api.getGoldenSet(id as number),
    enabled: typeof id === "number",
  });
}

/**
 * Everything a completed run invalidates.
 *
 * Listed once rather than at each call site, because a forgotten key here
 * shows up as a dashboard that silently disagrees with the run list.
 */
function useInvalidateRunScope() {
  const client = useQueryClient();
  return () => {
    for (const key of [
      keys.dashboard,
      keys.runs,
      keys.cutoffs,
      keys.system,
      ["trends"],
      ["drift-events"],
    ]) {
      void client.invalidateQueries({ queryKey: key as readonly unknown[] });
    }
  };
}

export function useRunEvaluation() {
  const invalidate = useInvalidateRunScope();
  return useMutation({
    mutationFn: (goldenSetId?: number) =>
      api.createRun(goldenSetId ? { golden_set_id: goldenSetId } : {}),
    onSuccess: invalidate,
  });
}

export function useCreateGoldenSet() {
  const client = useQueryClient();
  const invalidate = useInvalidateRunScope();
  return useMutation({
    mutationFn: (input: GoldenSetInput) => api.createGoldenSet(input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.goldenSets });
      invalidate();
    },
  });
}

export function useUpdateGoldenSet() {
  const client = useQueryClient();
  const invalidate = useInvalidateRunScope();
  return useMutation({
    mutationFn: ({ id, input }: { id: number; input: GoldenSetInput }) =>
      api.updateGoldenSet(id, input),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.goldenSets });
      invalidate();
    },
  });
}

export function useActivateGoldenSet() {
  const client = useQueryClient();
  const invalidate = useInvalidateRunScope();
  return useMutation({
    mutationFn: (id: number) => api.activateGoldenSet(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.goldenSets });
      invalidate();
    },
  });
}

export function useDeleteGoldenSet() {
  const client = useQueryClient();
  const invalidate = useInvalidateRunScope();
  return useMutation({
    mutationFn: (id: number) => api.deleteGoldenSet(id),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.goldenSets });
      invalidate();
    },
  });
}
