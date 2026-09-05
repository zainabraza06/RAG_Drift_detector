/**
 * Presentation metadata for domain enums.
 *
 * Kept out of component files so those export only components — which is what
 * lets Fast Refresh swap them without remounting — and so the label, tone and
 * icon vocabulary lives in exactly one place.
 *
 * Note what is *not* here: no raw colour values. Everything resolves to a
 * semantic token, so a palette change never has to be chased through enums.
 */

import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  CircleSlash,
  Minus,
  TrendingDown,
  TrendingUp,
  type LucideIcon,
} from "lucide-react";

import type { Tone } from "@/components/ui/Badge";
import type { DriftVerdict, EvidenceStrength, HealthStatus } from "@/lib/types";

export interface HealthMeta {
  label: string;
  hint: string;
  icon: LucideIcon;
  tone: Tone;
  /** Solid colour, for the status dot and the header accent rule. */
  solid: string;
}

/**
 * "Unknown" is deliberately not a success tone.
 *
 * A system that has never been compared against a baseline is not *known* to
 * be healthy, and colouring it green would be a claim the data cannot support.
 * The backend draws the same distinction.
 */
export const HEALTH_META: Record<HealthStatus, HealthMeta> = {
  healthy: {
    label: "Healthy",
    hint: "The latest run showed no significant change from its baseline.",
    icon: CheckCircle2,
    tone: "success",
    solid: "bg-success",
  },
  warning: {
    label: "Caution",
    hint: "No regression detected, but the assessment came with caveats.",
    icon: AlertTriangle,
    tone: "warning",
    solid: "bg-warning",
  },
  critical: {
    label: "Action needed",
    hint: "The latest run fell significantly below its baseline.",
    icon: TrendingDown,
    tone: "danger",
    solid: "bg-danger",
  },
  unknown: {
    label: "Not established",
    hint: "Not enough comparable history yet to judge retrieval health.",
    icon: CircleDashed,
    tone: "neutral",
    solid: "bg-ink-disabled",
  },
};

export interface VerdictMeta {
  label: string;
  tone: Tone;
  icon: LucideIcon;
  /** Left rail colour on a timeline row. */
  rail: string;
}

export const VERDICT_META: Record<DriftVerdict, VerdictMeta> = {
  degraded: {
    label: "Regression",
    tone: "danger",
    icon: TrendingDown,
    rail: "bg-danger",
  },
  improved: {
    label: "Improved",
    tone: "success",
    icon: TrendingUp,
    rail: "bg-success",
  },
  stable: { label: "Stable", tone: "neutral", icon: Minus, rail: "bg-line-strong" },
  insufficient_data: {
    label: "No baseline",
    tone: "neutral",
    icon: CircleSlash,
    rail: "bg-line-strong",
  },
};

export interface StrengthMeta {
  label: string;
  explanation: string;
  tone: Tone;
  rail: string;
}

/**
 * Strength is ordinal and renders as a *word*, never a bar or a percentage.
 *
 * The backend refuses to attach a numeric confidence to a heuristic, and a UI
 * could trivially reintroduce one by drawing three-quarters of a progress bar
 * beside "direct". These labels describe how directly an observation links to
 * the queries that broke — nothing about how likely it is to be the cause.
 */
export const STRENGTH_META: Record<EvidenceStrength, StrengthMeta> = {
  direct: {
    label: "Direct",
    explanation:
      "A verified fact that mechanically accounts for specific failing queries.",
    tone: "danger",
    rail: "bg-danger",
  },
  circumstantial: {
    label: "Circumstantial",
    explanation:
      "A verified change with a plausible mechanism, but no demonstrated link to these failures.",
    tone: "warning",
    rail: "bg-warning",
  },
  contextual: {
    label: "Context",
    explanation:
      "Describes the shape of the regression rather than proposing a cause.",
    tone: "neutral",
    rail: "bg-line-strong",
  },
};

export const RULE_LABELS: Record<string, string> = {
  missing_expected_documents: "Missing documents",
  embedding_model_changed: "Embedding model",
  expected_documents_demoted: "Ranking displacement",
  corpus_size_changed: "Corpus size",
  regression_shape: "Regression shape",
};
