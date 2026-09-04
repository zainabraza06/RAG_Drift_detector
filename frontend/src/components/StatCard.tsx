import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import type { ReactNode } from "react";

import { Tooltip } from "@/components/ui/Tooltip";
import { cn } from "@/lib/cn";
import { formatDelta, formatMetric } from "@/lib/format";

interface StatCardProps {
  label: string;
  value: number | null;
  delta?: number | null;
  hint?: string;
  /** Marks the metric the drift verdict was decided on. */
  primary?: boolean;
  footer?: ReactNode;
}

/**
 * One headline metric with its change since the previous comparable run.
 *
 * The delta is shown in *points*, and it is deliberately colour-coded but not
 * given a verdict: whether a change is real is the drift detector's call, and
 * a stat card that shouted "regression" on any red number would contradict it.
 */
export function StatCard({
  label,
  value,
  delta,
  hint,
  primary,
  footer,
}: StatCardProps) {
  const hasDelta = delta !== null && delta !== undefined;
  const isFlat = !hasDelta || Math.abs(delta) < 0.0005;
  const DeltaIcon = isFlat ? Minus : delta! > 0 ? ArrowUpRight : ArrowDownRight;

  return (
    <div
      className={cn(
        "group relative overflow-hidden rounded-xl border bg-surface p-5 shadow-card",
        "transition-[border-color,box-shadow] duration-200 hover:border-line-strong hover:shadow-raised",
        primary ? "border-brand/35" : "border-line",
      )}
    >
      {primary ? (
        <span
          className="absolute inset-x-0 top-0 h-0.5 bg-brand"
          aria-hidden
        />
      ) : null}

      <div className="flex items-center justify-between gap-2">
        <p className="text-xs font-medium uppercase tracking-wide text-content-muted">
          {hint ? (
            <Tooltip content={hint}>
              <span className="cursor-help border-b border-dotted border-line-strong">
                {label}
              </span>
            </Tooltip>
          ) : (
            label
          )}
        </p>
        {primary ? (
          <span className="rounded bg-brand-soft px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide text-brand">
            Primary
          </span>
        ) : null}
      </div>

      <p className="tnum mt-3 text-stat font-semibold text-content">
        {formatMetric(value)}
      </p>

      {hasDelta ? (
        <p
          className={cn(
            "tnum mt-2 inline-flex items-center gap-1 text-xs font-medium",
            isFlat
              ? "text-content-subtle"
              : delta! > 0
                ? "text-healthy"
                : "text-critical",
          )}
        >
          <DeltaIcon className="h-3.5 w-3.5" aria-hidden />
          {formatDelta(delta)}
          <span className="font-normal text-content-subtle">vs previous</span>
        </p>
      ) : (
        <p className="mt-2 text-xs text-content-subtle">No comparable prior run</p>
      )}

      {footer ? <div className="mt-3">{footer}</div> : null}
    </div>
  );
}
