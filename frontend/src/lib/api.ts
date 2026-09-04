/**
 * HTTP client.
 *
 * The backend returns one error envelope for every failure:
 *
 *   { "error": { "code": "run_not_found", "message": "...", "detail": [...] } }
 *
 * `ApiError` preserves that structure so the UI can branch on `code` and show
 * `message` — never parse prose, never surface a raw stack trace to a user.
 */

import type {
  DashboardSummary,
  DiagnosticReport,
  DriftAssessment,
  DriftVerdict,
  GoldenSetInput,
  MetricName,
  MetricSeries,
  Page,
  RunDetail,
  RunRecord,
  StoredGoldenSet,
  SystemInfo,
} from "./types";

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";

export interface ApiErrorDetail {
  field: string;
  message: string;
}

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly detail?: ApiErrorDetail[];

  constructor(
    status: number,
    code: string,
    message: string,
    detail?: ApiErrorDetail[],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }

  /** True when retrying could plausibly succeed (the store was down, etc.). */
  get isTransient(): boolean {
    return this.status >= 500 || this.status === 503;
  }

  /** True when the user has to change something before retrying. */
  get isUserFixable(): boolean {
    return this.status === 400 || this.status === 409 || this.status === 422;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      headers: { "Content-Type": "application/json", ...init?.headers },
      ...init,
    });
  } catch (cause) {
    // A network failure has no envelope, so it gets a synthetic one rather
    // than a raw TypeError reaching a component.
    throw new ApiError(
      0,
      "network_error",
      "Could not reach the API. Check that the backend is running.",
    );
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const body = await response.json().catch(() => null);

  if (!response.ok) {
    const envelope = body?.error;
    throw new ApiError(
      response.status,
      envelope?.code ?? "unknown_error",
      envelope?.message ?? `Request failed with status ${response.status}.`,
      envelope?.detail,
    );
  }

  return body as T;
}

function query(params: Record<string, string | number | boolean | undefined>) {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : "";
}

export const api = {
  // -- System ----------------------------------------------------------
  dashboard: () => request<DashboardSummary>("/dashboard"),
  systemInfo: () => request<SystemInfo>("/system/info"),

  // -- Runs ------------------------------------------------------------
  listRuns: (params: { limit?: number; offset?: number } = {}) =>
    request<Page<RunRecord>>(`/runs${query(params)}`),
  getRun: (runId: string) => request<RunRecord>(`/runs/${runId}`),
  getRunDetail: (runId: string) => request<RunDetail>(`/runs/${runId}/queries`),
  createRun: (body: { golden_set_id?: number } = {}) =>
    request<RunRecord>("/runs", {
      method: "POST",
      body: JSON.stringify({ trigger: "api", ...body }),
    }),
  deleteRun: (runId: string) =>
    request<void>(`/runs/${runId}`, { method: "DELETE" }),

  // -- Metrics ---------------------------------------------------------
  metricTrends: (params: { k: number; limit?: number }) =>
    request<MetricSeries[]>(`/metrics/trends${query(params)}`),
  metricSeries: (params: { metric: MetricName; k: number; limit?: number }) =>
    request<MetricSeries>(`/metrics/series${query(params)}`),
  cutoffs: () => request<number[]>("/metrics/cutoffs"),

  // -- Drift -----------------------------------------------------------
  runDrift: (runId: string) => request<DriftAssessment>(`/runs/${runId}/drift`),
  runDiagnostics: (runId: string) =>
    request<DiagnosticReport>(`/runs/${runId}/diagnostics`),
  driftEvents: (
    params: { limit?: number; offset?: number; verdict?: DriftVerdict } = {},
  ) => request<Page<DriftAssessment>>(`/drift/events${query(params)}`),
  latestDrift: () => request<DriftAssessment | null>("/drift/latest"),

  // -- Golden sets -----------------------------------------------------
  listGoldenSets: (params: { limit?: number } = {}) =>
    request<Page<StoredGoldenSet>>(`/golden-sets${query(params)}`),
  getGoldenSet: (id: number) => request<StoredGoldenSet>(`/golden-sets/${id}`),
  activeGoldenSet: () => request<StoredGoldenSet>("/golden-sets/active"),
  createGoldenSet: (body: GoldenSetInput) =>
    request<StoredGoldenSet>("/golden-sets", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  updateGoldenSet: (id: number, body: GoldenSetInput) =>
    request<StoredGoldenSet>(`/golden-sets/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  activateGoldenSet: (id: number) =>
    request<StoredGoldenSet>(`/golden-sets/${id}/activate`, { method: "POST" }),
  deleteGoldenSet: (id: number) =>
    request<void>(`/golden-sets/${id}`, { method: "DELETE" }),
};
