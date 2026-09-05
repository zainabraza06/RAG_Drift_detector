import { ArrowDown, ArrowUp, Minus } from "lucide-react";
import type { ReactNode } from "react";

import { Explained } from "@/components/ui/Tooltip";
import { cn } from "@/lib/cn";
import { formatDelta, formatMetric } from "@/lib/format";

interface StatCardProps {
  label: string;
  value: number | null;
  delta?: number | null;
  hint?: string;
  /** Marks the metric the drift verdict was decided on. */
  primary?: boolean;
  /** What the delta is measured against, e.g. "baseline". */
  comparedTo?: string;
  footer?: ReactNode;
}

/**
 * One headline metric and its change.
 *
 * The delta is coloured but carries no verdict: whether a change is real is
 * the drift detector's call, and a card that shouted "regression" at any red
 * number would routinely contradict it. The primary metric is marked with a
 * label rather than a different colour, so the distinction survives greyscale.
 */
export function StatCard({
  label,
  value,
  delta,
  hint,
  primary,
  comparedTo = "previous",
  footer,
}: StatCardProps) {
  const hasDelta = delta !== null && delta !== undefined;
  const isFlat = !hasDelta || Math.abs(delta) < 0.0005;
  const DeltaIcon = isFlat ? Minus : delta! > 0 ? ArrowUp : ArrowDown;

  return (
    <div
      className={cn(
        "group relative rounded-lg border bg-surface px-5 py-4 shadow-xs",
        "transition-colors duration-fast ease-out hover:border-line-strong",
        primary ? "border-accent-line" : "border-line",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-label text-ink-tertiary">
          {hint ? <Explained content={hint}>{label}</Explained> : label}
        </p>
        {primary ? (
          <span className="rounded-sm bg-accent-subtle px-1.5 py-0.5 text-micro uppercase text-accent-text">
            Primary
          </span>
        ) : null}
      </div>

      <p className="tnum mt-3 text-metric text-ink">{formatMetric(value)}</p>

      {hasDelta ? (
        <p className="mt-2 flex flex-wrap items-center gap-x-1.5 text-small">
          <span
            className={cn(
              "tnum inline-flex items-center gap-0.5 font-medium",
              isFlat
                ? "text-ink-tertiary"
                : delta! > 0
                  ? "text-success-text"
                  : "text-danger-text",
            )}
          >
            <DeltaIcon className="h-3 w-3" aria-hidden />
            {formatDelta(delta)}
          </span>
          <span className="text-ink-tertiary">vs {comparedTo}</span>
        </p>
      ) : (
        <p className="mt-2 text-small text-ink-tertiary">No comparable prior run</p>
      )}

      {footer ? <div className="mt-3">{footer}</div> : null}
    </div>
  );
}
