/**
 * Presentation metadata for domain enums.
 *
 * Kept out of the component files so those export only components — which is
 * what lets Fast Refresh replace them without remounting the tree, and keeps
 * the label/colour vocabulary in one place rather than beside the first
 * component that happened to need it.
 */

import {
  AlertTriangle,
  CheckCircle2,
  CircleSlash,
  HelpCircle,
  Minus,
  TrendingDown,
  TrendingUp,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import type { Tone } from "@/components/ui/Badge";
import type { DriftVerdict, EvidenceStrength, HealthStatus } from "@/lib/types";

export interface HealthMeta {
  label: string;
  hint: string;
  icon: LucideIcon;
  dot: string;
  chip: string;
}

/**
 * "Unknown" is deliberately not green.
 *
 * A system that has never been compared against a baseline is not *known* to
 * be healthy, and showing it as healthy would be a claim the data does not
 * support. The backend makes the same distinction.
 */
export const HEALTH_META: Record<HealthStatus, HealthMeta> = {
  healthy: {
    label: "Healthy",
    hint: "The latest run showed no significant change from its baseline.",
    icon: CheckCircle2,
    dot: "bg-healthy",
    chip: "bg-healthy-soft text-healthy ring-healthy/25",
  },
  warning: {
    label: "Caution",
    hint: "No regression detected, but the assessment came with caveats.",
    icon: AlertTriangle,
    dot: "bg-warning",
    chip: "bg-warning-soft text-warning ring-warning/25",
  },
  critical: {
    label: "Regression",
    hint: "The latest run fell significantly below its baseline.",
    icon: XCircle,
    dot: "bg-critical",
    chip: "bg-critical-soft text-critical ring-critical/25",
  },
  unknown: {
    label: "Not established",
    hint: "Not enough comparable history yet to judge retrieval health.",
    icon: HelpCircle,
    dot: "bg-unknown",
    chip: "bg-unknown-soft text-content-muted ring-unknown/20",
  },
};

export interface VerdictMeta {
  label: string;
  tone: Tone;
  icon: LucideIcon;
}

export const VERDICT_META: Record<DriftVerdict, VerdictMeta> = {
  degraded: { label: "Regression", tone: "critical", icon: TrendingDown },
  improved: { label: "Improved", tone: "healthy", icon: TrendingUp },
  stable: { label: "Stable", tone: "healthy", icon: Minus },
  insufficient_data: { label: "Not enough data", tone: "neutral", icon: CircleSlash },
};

export interface StrengthMeta {
  label: string;
  explanation: string;
  chip: string;
  rail: string;
}

/**
 * Strength is ordinal and is rendered as a *word*, never a bar or a percentage.
 *
 * The backend refuses to attach a numeric confidence to a heuristic, and it
 * would be trivial for a UI to reintroduce one by drawing three-quarters of a
 * progress bar next to "direct". These labels say how directly the observation
 * links to the queries that broke — nothing about how likely it is to be the
 * cause.
 */
export const STRENGTH_META: Record<EvidenceStrength, StrengthMeta> = {
  direct: {
    label: "Direct",
    explanation:
      "A verified fact that mechanically accounts for specific failing queries.",
    chip: "bg-critical-soft text-critical ring-critical/25",
    rail: "bg-critical",
  },
  circumstantial: {
    label: "Circumstantial",
    explanation:
      "A verified change with a plausible mechanism, but no demonstrated link to these failures.",
    chip: "bg-warning-soft text-warning ring-warning/25",
    rail: "bg-warning",
  },
  contextual: {
    label: "Context",
    explanation:
      "Describes the shape of the regression rather than proposing a cause.",
    chip: "bg-unknown-soft text-content-muted ring-unknown/20",
    rail: "bg-unknown",
  },
};

export const RULE_LABELS: Record<string, string> = {
  missing_expected_documents: "Missing documents",
  embedding_model_changed: "Embedding model",
  expected_documents_demoted: "Ranking displacement",
  corpus_size_changed: "Corpus size",
  regression_shape: "Regression shape",
};
