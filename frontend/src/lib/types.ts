/**
 * API types.
 *
 * These mirror the Pydantic models the backend serialises. They are written by
 * hand rather than generated so they can carry the same explanatory comments
 * the Python side does — in particular around the boundary between what is a
 * statistical claim and what is a heuristic.
 */

export type MetricName = "recall_at_k" | "precision_at_k" | "mrr" | "ndcg_at_k";

export const METRIC_NAMES: readonly MetricName[] = [
  "recall_at_k",
  "precision_at_k",
  "mrr",
  "ndcg_at_k",
] as const;

export const METRIC_LABELS: Record<MetricName, string> = {
  recall_at_k: "Recall",
  precision_at_k: "Precision",
  mrr: "MRR",
  ndcg_at_k: "NDCG",
};

/** How each metric responds, in one line, for the chart legend and tooltips. */
export const METRIC_DESCRIPTIONS: Record<MetricName, string> = {
  recall_at_k: "Share of expected documents found in the top k. Blind to ordering.",
  precision_at_k: "Share of the top k that was relevant.",
  mrr: "How high the first correct document ranked, averaged over queries.",
  ndcg_at_k: "Ranking quality with graded relevance. Sensitive to order.",
};

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface GoldenSetRef {
  name: string;
  version: string;
  fingerprint: string;
}

export interface MetricSet {
  k: number;
  query_count: number;
  recall_at_k: number;
  precision_at_k: number;
  mrr: number;
  ndcg_at_k: number;
}

export interface VectorStoreInfo {
  connector: string;
  collection: string;
  document_count: number;
  embedding_model: string | null;
  embedding_dimensions: number | null;
  extra: Record<string, string | number | boolean | null>;
}

export interface RunRecord {
  run_id: string;
  golden_set: GoldenSetRef;
  query_count: number;
  primary_k: number;
  metrics: MetricSet[];
  store: VectorStoreInfo;
  started_at: string;
  finished_at: string;
  duration_ms: number;
  trigger: string;
}

export interface QueryScore {
  query_id: string;
  query: string;
  k: number;
  retrieved_ids: string[];
  relevant_ids: string[];
  hits: number;
  recall_at_k: number;
  precision_at_k: number;
  reciprocal_rank: number;
  ndcg_at_k: number;
  first_relevant_rank: number | null;
  latency_ms: number | null;
}

export interface RunDetail {
  run: RunRecord;
  query_scores: QueryScore[];
}

export interface MetricPoint {
  run_id: string;
  recorded_at: string;
  value: number;
  document_count: number;
  golden_set_fingerprint: string;
}

export interface MetricSeries {
  metric: MetricName;
  k: number;
  points: MetricPoint[];
}

// ----------------------------------------------------------------------
// Drift — statistical claims
// ----------------------------------------------------------------------

export type DriftVerdict = "stable" | "degraded" | "improved" | "insufficient_data";

export interface MetricComparison {
  metric: MetricName;
  k: number;
  baseline_value: number;
  current_value: number;
  difference: number;
  relative_change: number | null;
  ci_lower: number;
  ci_upper: number;
  confidence_level: number;
  standard_error: number;
  p_value: number;
  p_value_degradation: number;
  p_value_adjusted: number;
  sample_size: number;
  resamples: number;
  method: string;
  /** The pre-specified endpoint the verdict was decided on. */
  is_primary: boolean;
  /** Adjusted p below alpha AND the interval excludes zero. */
  significant: boolean;
  /** The change is large enough to be worth acting on. */
  material: boolean;
  direction: "up" | "down" | "flat";
}

export interface HitRateComparison {
  k: number;
  baseline_hit_rate: number;
  current_hit_rate: number;
  became_misses: number;
  became_hits: number;
  unchanged: number;
  discordant: number;
  p_value: number;
  p_value_adjusted: number;
  significant: boolean;
  test: string;
}

export interface DriftConfig {
  confidence_level: number;
  resamples: number;
  seed: number;
  baseline_window: number;
  min_queries: number;
  min_effect: number;
  interval_method: string;
  primary_metric: MetricName;
  correct_multiple_comparisons: boolean;
}

// ----------------------------------------------------------------------
// Diagnostics — heuristics, deliberately NOT statistical claims
// ----------------------------------------------------------------------

/**
 * Ordinal, never numeric. The backend refuses to attach a confidence value to
 * a diagnostic, and the UI must not invent one by rendering these as a
 * percentage or a progress bar.
 */
export type EvidenceStrength = "direct" | "circumstantial" | "contextual";

export interface DiagnosticFinding {
  rule_id: string;
  title: string;
  summary: string;
  strength: EvidenceStrength;
  /** Queries this finding accounts for. Arithmetic, not inference. */
  explains: number | null;
  out_of: number | null;
  evidence: Record<string, string | number | boolean | string[]>;
  suggested_action: string | null;
}

export interface DiagnosticReport {
  run_id: string;
  /** Always "heuristic". Present so a client cannot mistake this for a test. */
  basis: string;
  disclaimer: string;
  findings: DiagnosticFinding[];
  /** Ran and found nothing — ruled out. */
  checks_passed: string[];
  /** Could not run, with the reason — unknown, which is not the same thing. */
  checks_skipped: Record<string, string>;
  generated_at: string;
}

export interface DriftAssessment {
  run_id: string;
  baseline_run_ids: string[];
  golden_set: GoldenSetRef;
  verdict: DriftVerdict;
  summary: string;
  comparisons: MetricComparison[];
  hit_rate: HitRateComparison | null;
  query_count: number;
  warnings: string[];
  config: DriftConfig;
  diagnostics: DiagnosticReport | null;
  detected_at: string;
}

// ----------------------------------------------------------------------
// Golden sets
// ----------------------------------------------------------------------

export interface ExpectedDocument {
  document_id: string;
  relevance: number;
}

export interface GoldenQuery {
  query_id: string;
  query: string;
  expected_documents: ExpectedDocument[];
  note: string | null;
}

export interface GoldenSet {
  name: string;
  version: string;
  description: string | null;
  created_at: string;
  queries: GoldenQuery[];
}

export interface StoredGoldenSet {
  golden_set_id: number;
  golden_set: GoldenSet;
  is_active: boolean;
  source: string;
  created_at: string;
}

export interface GoldenSetInput {
  name: string;
  version: string;
  description: string | null;
  queries: {
    query_id: string | null;
    query: string;
    expected_documents: ExpectedDocument[];
    note: string | null;
  }[];
  activate: boolean;
}

// ----------------------------------------------------------------------
// System
// ----------------------------------------------------------------------

export type HealthStatus = "healthy" | "warning" | "critical" | "unknown";

export interface DashboardSummary {
  has_runs: boolean;
  total_runs: number;
  latest_run: RunRecord | null;
  previous_run: RunRecord | null;
  primary_metrics: MetricSet | null;
  metric_deltas: Partial<Record<MetricName, number>>;
  active_golden_set: StoredGoldenSet | null;
  last_run_at: string | null;
  document_count: number | null;
  health: HealthStatus;
  latest_drift: DriftAssessment | null;
  open_regressions: number;
}

export interface VectorStoreStatus {
  connector: string;
  collection: string;
  reachable: boolean;
  document_count: number | null;
  embedding_model: string | null;
  embedding_dimensions: number | null;
  message: string | null;
}

export interface SystemInfo {
  app_name: string;
  version: string;
  environment: string;
  schema_revision: string | null;
  vector_store: VectorStoreStatus;
  available_connectors: string[];
  available_embedding_providers: string[];
  eval_k_values: number[];
  eval_primary_k: number;
  run_count: number;
  golden_set_count: number;
  active_golden_set: GoldenSetRef | null;
}
