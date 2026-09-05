import { ArrowDown, ArrowUp, Info, Minus } from "lucide-react";

import { Badge } from "@/components/ui/Badge";
import { Explained, Tooltip } from "@/components/ui/Tooltip";
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
 * Everything here arrives with its interval and its p-value, because a verdict
 * a reader cannot argue with is an assertion rather than evidence. The
 * heuristic half lives in a separate component with separate framing.
 */
export function DriftAssessmentCard({
  assessment,
  compact,
  hideSummary,
}: {
  assessment: DriftAssessment;
  compact?: boolean;
  /** The caller already showed the summary; do not repeat it. */
  hideSummary?: boolean;
}) {
  const primary = assessment.comparisons.find((c) => c.is_primary);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center gap-2">
        <VerdictBadge verdict={assessment.verdict} />
        {primary ? (
          <Badge tone="accent">
            decided on {METRIC_LABELS[primary.metric]}
            {primary.metric === "mrr" ? "" : `@${primary.k}`}
          </Badge>
        ) : null}
        <span className="text-small text-ink-tertiary">
          {formatDateTime(assessment.detected_at)}
        </span>
      </div>

      {hideSummary ? null : (
        <p className="max-w-prose text-body text-ink">{assessment.summary}</p>
      )}

      {assessment.comparisons.length > 0 ? (
        <ComparisonTable comparisons={assessment.comparisons} />
      ) : null}

      {!compact && assessment.hit_rate ? (
        <HitRateSummary assessment={assessment} />
      ) : null}

      {assessment.warnings.length > 0 ? (
        <ul className="space-y-2">
          {assessment.warnings.map((warning) => (
            <li
              key={warning}
              className="flex gap-2 rounded-md border border-warning-line bg-warning-subtle px-3 py-2 text-small leading-5 text-warning-text"
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

/**
 * A borderless table: rules between rows only, no vertical lines, no zebra.
 * Alignment does the separating, which is what keeps dense numeric data
 * scannable instead of caged.
 */
function ComparisonTable({ comparisons }: { comparisons: MetricComparison[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[40rem] text-body">
        <thead>
          <tr className="border-b border-line text-left align-bottom">
            <Th>Metric</Th>
            <Th align="right">Baseline</Th>
            <Th align="right">Current</Th>
            <Th align="right">Change</Th>
            <Th>
              <Explained content="If this procedure were repeated on fresh samples of queries, about 95% of the intervals produced would contain the true change.">
                95% CI
              </Explained>
            </Th>
            <Th align="right">
              <Explained content="Two-sided, after multiple-comparison correction for the supporting metrics. The primary metric is one pre-specified test and is not penalised.">
                p
              </Explained>
            </Th>
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

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right";
}) {
  return (
    <th
      scope="col"
      className={cn(
        "px-3 pb-2 text-micro uppercase text-ink-tertiary",
        align === "right" ? "text-right" : "text-left",
        "first:pl-0 last:pr-1",
      )}
    >
      {children}
    </th>
  );
}

function ComparisonRow({ comparison }: { comparison: MetricComparison }) {
  const down = comparison.direction === "down";
  const ChangeIcon = comparison.direction === "flat" ? Minus : down ? ArrowDown : ArrowUp;

  return (
    <tr className="border-b border-line-subtle last:border-0">
      <td className="py-2.5 pr-2">
        <span className="flex items-center gap-2">
          <span
            className={cn(
              "text-body",
              comparison.is_primary ? "font-semibold text-ink" : "text-ink-secondary",
            )}
          >
            {METRIC_LABELS[comparison.metric]}
            {comparison.metric === "mrr" ? "" : `@${comparison.k}`}
          </span>
          {comparison.is_primary ? (
            <Tooltip content="The pre-specified endpoint the verdict rests on. It is tested at full alpha; the others carry a multiple-comparison correction and are supporting context.">
              <span className="cursor-help rounded-sm bg-accent-subtle px-1 py-px text-micro uppercase text-accent-text">
                primary
              </span>
            </Tooltip>
          ) : null}
        </span>
      </td>
      <td className="tnum px-2 py-2.5 text-right text-ink-tertiary">
        {formatMetric(comparison.baseline_value)}
      </td>
      <td className="tnum px-2 py-2.5 text-right font-medium text-ink">
        {formatMetric(comparison.current_value)}
      </td>
      <td
        className={cn(
          "tnum px-2 py-2.5 text-right font-medium",
          comparison.direction === "flat"
            ? "text-ink-tertiary"
            : down
              ? "text-danger-text"
              : "text-success-text",
        )}
      >
        <span className="inline-flex items-center gap-0.5">
          <ChangeIcon className="h-3 w-3" aria-hidden />
          {Math.abs(comparison.difference * 100).toFixed(1)} pts
        </span>
      </td>
      <td className="tnum px-2 py-2.5 font-mono text-[11px] text-ink-tertiary">
        {formatInterval(comparison.ci_lower, comparison.ci_upper)}
      </td>
      <td className="py-2.5 pl-3 pr-1 text-right">
        <span
          className={cn(
            "tnum font-mono text-[11px]",
            comparison.significant ? "font-semibold text-ink" : "text-ink-tertiary",
          )}
        >
          {comparison.p_value_adjusted < 0.0001
            ? "<0.0001"
            : comparison.p_value_adjusted.toFixed(4)}
        </span>
        <SignificanceNote comparison={comparison} />
      </td>
    </tr>
  );
}

/**
 * Significance and materiality are shown separately, never merged.
 *
 * A change can be statistically real and operationally irrelevant; one badge
 * covering both would hide exactly the distinction the detector makes.
 */
function SignificanceNote({ comparison }: { comparison: MetricComparison }) {
  if (comparison.significant === comparison.material) return null;

  return (
    <Tooltip
      content={
        comparison.significant
          ? "Statistically distinguishable from noise, but smaller than the threshold worth acting on."
          : "Large enough to matter, but not distinguishable from noise at this sample size."
      }
    >
      <span className="ml-1.5 cursor-help text-micro uppercase text-ink-tertiary">
        {comparison.significant ? "sub-threshold" : "n.s."}
      </span>
    </Tooltip>
  );
}

function HitRateSummary({ assessment }: { assessment: DriftAssessment }) {
  const hit = assessment.hit_rate;
  if (!hit) return null;

  return (
    <div className="rounded-md border border-line-subtle bg-inset px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="text-micro uppercase text-ink-tertiary">
          Queries returning anything relevant
        </h4>
        <span className="tnum text-body font-medium text-ink">
          {formatPercent(hit.baseline_hit_rate)} → {formatPercent(hit.current_hit_rate)}
        </span>
      </div>
      <p className="mt-2 max-w-prose text-small leading-5 text-ink-secondary">
        {hit.became_misses} stopped working, {hit.became_hits} started.{" "}
        <Explained content="McNemar's exact test, not a two-proportion z-test: both runs score the same queries, so they are not independent samples. With only a few discordant pairs the smallest achievable p can sit above 0.05 no matter how one-sided the evidence.">
          McNemar exact
        </Explained>{" "}
        <span className="tnum font-mono text-[11px]">{formatPValue(hit.p_value)}</span>
        {!hit.significant && hit.discordant > 0 ? (
          <span className="text-ink-tertiary">
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
    <p className="max-w-prose border-t border-line-subtle pt-4 text-label leading-5 text-ink-tertiary">
      Paired bootstrap over {query_count} queries, {config.resamples.toLocaleString()}{" "}
      resamples, {config.interval_method.toUpperCase()} intervals at{" "}
      {formatPercent(config.confidence_level)}. Baseline is the mean of{" "}
      {baseline_run_ids.length} earlier run{baseline_run_ids.length === 1 ? "" : "s"}{" "}
      scored against the same golden set. Seed {config.seed} — the same inputs always
      produce the same verdict.
    </p>
  );
}
