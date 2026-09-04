import type {
  DashboardSummary,
  DiagnosticReport,
  DriftAssessment,
  MetricComparison,
} from "@/lib/types";

export function comparison(
  overrides: Partial<MetricComparison> = {},
): MetricComparison {
  return {
    metric: "ndcg_at_k",
    k: 5,
    baseline_value: 0.958,
    current_value: 0.765,
    difference: -0.193,
    relative_change: -0.2,
    ci_lower: -0.362,
    ci_upper: -0.086,
    confidence_level: 0.95,
    standard_error: 0.07,
    p_value: 0.0089,
    p_value_degradation: 0.0044,
    p_value_adjusted: 0.0089,
    sample_size: 30,
    resamples: 10000,
    method: "bca",
    is_primary: true,
    significant: true,
    material: true,
    direction: "down",
    ...overrides,
  };
}

export function diagnostics(
  overrides: Partial<DiagnosticReport> = {},
): DiagnosticReport {
  return {
    run_id: "run-1",
    basis: "heuristic",
    disclaimer:
      "Diagnostics are heuristics, not statistical findings. They report facts that changed alongside the regression.",
    findings: [
      {
        rule_id: "missing_expected_documents",
        title: "Expected documents missing from the index",
        summary:
          "6 document(s) the golden set expects are absent from the index. 5 of the 5 queries that stopped retrieving anything relevant expect at least one of them.",
        strength: "direct",
        explains: 5,
        out_of: 5,
        evidence: { missing_document_ids: ["doc-api-001", "doc-api-002"] },
        suggested_action: "Check whether the last indexing job dropped these documents.",
      },
      {
        rule_id: "corpus_size_changed",
        title: "Indexed document count changed",
        summary: "The index shrank from 32 to 26 documents (-19%).",
        strength: "circumstantial",
        explains: null,
        out_of: null,
        evidence: {},
        suggested_action: null,
      },
    ],
    checks_passed: ["embedding_model_changed", "expected_documents_demoted"],
    checks_skipped: {},
    generated_at: "2026-09-04T12:00:00Z",
    ...overrides,
  };
}

export function assessment(
  overrides: Partial<DriftAssessment> = {},
): DriftAssessment {
  return {
    run_id: "run-1",
    baseline_run_ids: ["run-0"],
    golden_set: { name: "acme", version: "1", fingerprint: "abc123" },
    verdict: "degraded",
    summary:
      "Retrieval quality regressed: NDCG@5 fell 19.3 points (0.958 to 0.765), 95% CI [-0.362, -0.086], p=0.0089.",
    comparisons: [
      comparison(),
      // A supporting metric: its own interval, and a Holm-adjusted p that
      // does not clear alpha even though the interval excludes zero.
      comparison({
        metric: "recall_at_k",
        is_primary: false,
        baseline_value: 0.933,
        current_value: 0.767,
        difference: -0.167,
        ci_lower: -0.3,
        ci_upper: -0.05,
        p_value: 0.0334,
        p_value_adjusted: 0.1002,
        significant: false,
      }),
    ],
    hit_rate: {
      k: 5,
      baseline_hit_rate: 1,
      current_hit_rate: 0.833,
      became_misses: 5,
      became_hits: 0,
      unchanged: 25,
      discordant: 5,
      p_value: 0.0625,
      p_value_adjusted: 0.0625,
      significant: false,
      test: "mcnemar_exact",
    },
    query_count: 30,
    warnings: [],
    config: {
      confidence_level: 0.95,
      resamples: 10000,
      seed: 20240517,
      baseline_window: 3,
      min_queries: 15,
      min_effect: 0.01,
      interval_method: "bca",
      primary_metric: "ndcg_at_k",
      correct_multiple_comparisons: true,
    },
    diagnostics: diagnostics(),
    detected_at: "2026-09-04T12:00:00Z",
    ...overrides,
  };
}

export function dashboard(
  overrides: Partial<DashboardSummary> = {},
): DashboardSummary {
  return {
    has_runs: true,
    total_runs: 4,
    latest_run: {
      run_id: "run-1",
      golden_set: { name: "acme", version: "1", fingerprint: "abc123" },
      query_count: 30,
      primary_k: 5,
      metrics: [
        {
          k: 5,
          query_count: 30,
          recall_at_k: 0.767,
          precision_at_k: 0.173,
          mrr: 0.768,
          ndcg_at_k: 0.765,
        },
      ],
      store: {
        connector: "chroma",
        collection: "demo",
        document_count: 26,
        embedding_model: "hashing-v1-d384",
        embedding_dimensions: 384,
        extra: {},
      },
      started_at: "2026-09-04T12:00:00Z",
      finished_at: "2026-09-04T12:00:02Z",
      duration_ms: 2100,
      trigger: "api",
    },
    previous_run: null,
    primary_metrics: {
      k: 5,
      query_count: 30,
      recall_at_k: 0.767,
      precision_at_k: 0.173,
      mrr: 0.768,
      ndcg_at_k: 0.765,
    },
    metric_deltas: { ndcg_at_k: -0.193, recall_at_k: -0.167 },
    active_golden_set: null,
    last_run_at: "2026-09-04T12:00:02Z",
    document_count: 26,
    health: "critical",
    latest_drift: assessment(),
    open_regressions: 1,
    ...overrides,
  };
}
