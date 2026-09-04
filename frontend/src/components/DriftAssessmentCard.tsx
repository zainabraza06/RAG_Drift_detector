import { ArrowDown, ArrowUp, Info, Minus } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Tooltip } from "@/components/ui/Tooltip";
import { cn } from "@/lib/cn";
import { VERDICT_META } from "@/lib/display";
import {
  formatDateTime,
  formatInterval,
  formatMetric,
  formatPValue,
  formatPercent,
} from "@/lib/format";
import type { DriftAssessment, DriftVerdict, MetricComparison } from "@/lib/types";
import { METRIC_LABELS } from "@/lib/types";

export function VerdictBadge({ verdict }: { verdict: DriftVerdict }) {
  const meta = VERDICT_META[verdict];
  const Icon = meta.icon;
  return (
    <Badge tone={meta.tone} icon={<Icon className="h-3 w-3" aria-hidden />}>
      {meta.label}
    </Badge>
  );
}

/**
 * The statistical half of an assessment.
 *
 * Everything shown here comes with its interval and its p-value, because a
 * verdict a reader cannot argue with is an assertion rather than evidence.
 * The heuristic half lives in a separate component with separate framing.
 */
export function DriftAssessmentCard({
  assessment,
  compact,
}: {
  assessment: DriftAssessment;
  compact?: boolean;
}) {
  const primary = assessment.comparisons.find((c) => c.is_primary);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <VerdictBadge verdict={assessment.verdict} />
        {primary ? (
          <Badge tone="brand">
            decided on {METRIC_LABELS[primary.metric]}
            {primary.metric === "mrr" ? "" : `@${primary.k}`}
          </Badge>
        ) : null}
        <span className="text-xs text-content-subtle">
          {formatDateTime(assessment.detected_at)}
        </span>
      </div>

      <p className="text-sm leading-relaxed text-content">{assessment.summary}</p>

      {assessment.comparisons.length > 0 ? (
        <ComparisonTable comparisons={assessment.comparisons} />
      ) : null}

      {!compact && assessment.hit_rate ? (
        <HitRateSummary assessment={assessment} />
      ) : null}

      {assessment.warnings.length > 0 ? (
        <ul className="space-y-1.5">
          {assessment.warnings.map((warning) => (
            <li
              key={warning}
              className="flex gap-2 rounded-lg bg-warning-soft px-3 py-2 text-xs leading-relaxed text-warning"
            >
              <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              {warning}
            </li>
          ))}
        </ul>
      ) : null}

      {!compact ? <MethodFootnote assessment={assessment} /> : null}
    </div>
  );
}

function ComparisonTable({ comparisons }: { comparisons: MetricComparison[] }) {
  return (
    <div className="-mx-1 overflow-x-auto">
      <table className="w-full min-w-[36rem] border-separate border-spacing-x-1 border-spacing-y-0 text-sm">
        <thead>
          <tr className="text-left text-2xs uppercase tracking-wide text-content-subtle">
            <th className="px-2 pb-2 font-medium">Metric</th>
            <th className="px-2 pb-2 text-right font-medium">Baseline</th>
            <th className="px-2 pb-2 text-right font-medium">Current</th>
            <th className="px-2 pb-2 text-right font-medium">Change</th>
            <th className="px-2 pb-2 font-medium">
              <Tooltip content="If this procedure were repeated on fresh samples of queries, about 95% of the intervals produced would contain the true change.">
                <span className="cursor-help border-b border-dotted border-line-strong">
                  95% CI
                </span>
              </Tooltip>
            </th>
            <th className="px-2 pb-2 text-right font-medium">p</th>
          </tr>
        </thead>
        <tbody>
          {comparisons.map((comparison) => (
            <ComparisonRow key={comparison.metric} comparison={comparison} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ComparisonRow({ comparison }: { comparison: MetricComparison }) {
  const down = comparison.direction === "down";
  const ChangeIcon = comparison.direction === "flat" ? Minus : down ? ArrowDown : ArrowUp;

  return (
    <tr
      className={cn(
        "align-middle",
        comparison.is_primary && "bg-brand-soft/40",
      )}
    >
      <td className="rounded-l-md px-2 py-2">
        <span className="flex items-center gap-1.5 font-medium text-content">
          {METRIC_LABELS[comparison.metric]}
          {comparison.metric === "mrr" ? "" : `@${comparison.k}`}
          {comparison.is_primary ? (
            <Tooltip content="The pre-specified endpoint the verdict rests on. It is tested at full alpha; the others carry a multiple-comparison correction and are supporting context.">
              <span className="cursor-help rounded bg-brand px-1 py-px text-2xs font-semibold uppercase text-brand-fg">
                primary
              </span>
            </Tooltip>
          ) : null}
        </span>
      </td>
      <td className="tnum px-2 py-2 text-right text-content-muted">
        {formatMetric(comparison.baseline_value)}
      </td>
      <td className="tnum px-2 py-2 text-right font-medium text-content">
        {formatMetric(comparison.current_value)}
      </td>
      <td
        className={cn(
          "tnum px-2 py-2 text-right font-medium",
          comparison.direction === "flat"
            ? "text-content-subtle"
            : down
              ? "text-critical"
              : "text-healthy",
        )}
      >
        <span className="inline-flex items-center gap-0.5">
          <ChangeIcon className="h-3 w-3" aria-hidden />
          {Math.abs(comparison.difference * 100).toFixed(1)} pts
        </span>
      </td>
      <td className="tnum px-2 py-2 font-mono text-xs text-content-muted">
        {formatInterval(comparison.ci_lower, comparison.ci_upper)}
      </td>
      <td className="tnum px-2 py-2 text-right">
        <span
          className={cn(
            "font-mono text-xs",
            comparison.significant ? "font-semibold text-content" : "text-content-subtle",
          )}
        >
          {comparison.p_value_adjusted < 0.0001
            ? "<0.0001"
            : comparison.p_value_adjusted.toFixed(4)}
        </span>
        <SignificanceFlags comparison={comparison} />
      </td>
    </tr>
  );
}

/**
 * Significance and materiality are shown separately, never merged.
 *
 * A change can be statistically real and operationally irrelevant; collapsing
 * the two into one badge would hide exactly the distinction the detector makes.
 */
function SignificanceFlags({ comparison }: { comparison: MetricComparison }) {
  if (comparison.significant && comparison.material) return null;
  if (!comparison.significant && !comparison.material) return null;

  return (
    <Tooltip
      content={
        comparison.significant
          ? "Statistically distinguishable from noise, but smaller than the threshold worth acting on."
          : "Large enough to matter, but not distinguishable from noise at this sample size."
      }
    >
      <span className="ml-1 cursor-help text-2xs text-content-subtle">
        {comparison.significant ? "below threshold" : "not significant"}
      </span>
    </Tooltip>
  );
}

function HitRateSummary({ assessment }: { assessment: DriftAssessment }) {
  const hit = assessment.hit_rate;
  if (!hit) return null;

  return (
    <div className="rounded-lg border border-line bg-surface-muted px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-xs font-semibold uppercase tracking-wide text-content-muted">
          Queries returning anything relevant
        </h4>
        <span className="tnum text-sm font-medium text-content">
          {formatPercent(hit.baseline_hit_rate)} → {formatPercent(hit.current_hit_rate)}
        </span>
      </div>
      <p className="mt-1.5 text-xs leading-relaxed text-content-muted">
        {hit.became_misses} stopped working, {hit.became_hits} started.{" "}
        <Tooltip content="McNemar's exact test, not a two-proportion z-test: both runs score the same queries, so they are not independent samples. With only a few discordant pairs the smallest achievable p can sit above 0.05 no matter how one-sided the evidence.">
          <span className="cursor-help border-b border-dotted border-line-strong">
            McNemar exact
          </span>
        </Tooltip>{" "}
        <span className="tnum font-mono">{formatPValue(hit.p_value)}</span>
        {!hit.significant && hit.discordant > 0 ? (
          <span className="text-content-subtle">
            {" "}
            — {hit.discordant} discordant pair{hit.discordant === 1 ? "" : "s"} is too
            few to reach significance.
          </span>
        ) : null}
      </p>
    </div>
  );
}

function MethodFootnote({ assessment }: { assessment: DriftAssessment }) {
  const { config, query_count, baseline_run_ids } = assessment;
  return (
    <p className="border-t border-line pt-3 text-2xs leading-relaxed text-content-subtle">
      Paired bootstrap over {query_count} queries, {config.resamples.toLocaleString()}{" "}
      resamples, {config.interval_method.toUpperCase()} intervals at{" "}
      {formatPercent(config.confidence_level)}. Baseline is the mean of{" "}
      {baseline_run_ids.length} earlier run{baseline_run_ids.length === 1 ? "" : "s"}{" "}
      scored against the same golden set. Seed {config.seed} — the same inputs always
      produce the same verdict.
    </p>
  );
}
