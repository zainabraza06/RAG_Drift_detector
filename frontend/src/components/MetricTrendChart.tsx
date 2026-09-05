import { useMemo } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ReferenceDot,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatChartTime, formatDateTime, formatMetric, shortId } from "@/lib/format";
import type { DriftVerdict, MetricName, MetricSeries } from "@/lib/types";
import { METRIC_DESCRIPTIONS, METRIC_LABELS } from "@/lib/types";
import { useChartTheme } from "@/lib/useChartTheme";

export interface TrendPoint {
  runId: string;
  recordedAt: string;
  value: number;
  documentCount: number;
  verdict: DriftVerdict | null;
}

interface MetricTrendChartProps {
  metric: MetricName;
  k: number;
  series: MetricSeries;
  verdicts: Map<string, DriftVerdict>;
  height?: number;
  onSelectRun?: (runId: string) => void;
}

/**
 * One metric over time, with regressions marked on the line itself.
 *
 * The y-axis is padded around the observed range rather than pinned to [0, 1]:
 * retrieval metrics usually sit in a narrow band near the top, and a full-range
 * axis flattens exactly the movement this tool exists to show. The axis still
 * never exceeds [0, 1], so the shape cannot be read as more dramatic than it is.
 */
export function MetricTrendChart({
  metric,
  k,
  series,
  verdicts,
  height = 200,
  onSelectRun,
}: MetricTrendChartProps) {
  const theme = useChartTheme();

  const data = useMemo<TrendPoint[]>(
    () =>
      series.points.map((point) => ({
        runId: point.run_id,
        recordedAt: point.recorded_at,
        value: point.value,
        documentCount: point.document_count,
        verdict: verdicts.get(point.run_id) ?? null,
      })),
    [series.points, verdicts],
  );

  const domain = useMemo<[number, number]>(() => {
    if (data.length === 0) return [0, 1];
    const values = data.map((point) => point.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const padding = Math.max((max - min) * 0.25, 0.02);
    return [Math.max(0, min - padding), Math.min(1, max + padding)];
  }, [data]);

  const regressions = data.filter((point) => point.verdict === "degraded");
  const gradientId = `gradient-${metric}-${k}`;

  return (
    <div className="rounded-lg border border-line bg-surface px-5 py-4 shadow-xs transition-colors duration-fast ease-out hover:border-line-strong">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-subheading text-ink">
          {METRIC_LABELS[metric]}
          {metric === "mrr" ? "" : `@${k}`}
        </h3>
        <span className="tnum text-body font-medium text-ink">
          {formatMetric(data.at(-1)?.value ?? null)}
        </span>
      </div>
      <p className="mb-5 mt-1 max-w-prose text-small text-ink-tertiary">
        {METRIC_DESCRIPTIONS[metric]}
      </p>

      <ResponsiveContainer width="100%" height={height}>
        <AreaChart data={data} margin={{ top: 6, right: 8, bottom: 0, left: -12 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={theme.accent} stopOpacity={0.14} />
              <stop offset="100%" stopColor={theme.accent} stopOpacity={0} />
            </linearGradient>
          </defs>

          <CartesianGrid stroke={theme.grid} strokeDasharray="2 4" vertical={false} />
          <XAxis
            dataKey="recordedAt"
            tickFormatter={formatChartTime}
            tick={{ fill: theme.axis, fontSize: 11 }}
            tickLine={false}
            axisLine={{ stroke: theme.grid }}
            minTickGap={28}
          />
          <YAxis
            domain={domain}
            tickFormatter={(value: number) => value.toFixed(2)}
            tick={{ fill: theme.axis, fontSize: 11 }}
            tickLine={false}
            axisLine={false}
            width={44}
          />
          <Tooltip
            cursor={{ stroke: theme.line, strokeWidth: 1 }}
            content={<TrendTooltip metric={metric} k={k} />}
          />

          <Area
            type="monotone"
            dataKey="value"
            stroke={theme.accent}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            // Dots only appear once the series is short enough for them to be
            // distinguishable; on a long history they turn into a smear.
            dot={data.length <= 24 ? { r: 2.5, fill: theme.accent, strokeWidth: 0 } : false}
            activeDot={{ r: 4, fill: theme.accent, stroke: theme.surface, strokeWidth: 2 }}
            isAnimationActive={data.length <= 60}
            animationDuration={420}
          />

          {regressions.map((point) => (
            <ReferenceDot
              key={point.runId}
              x={point.recordedAt}
              y={point.value}
              r={5}
              fill={theme.danger}
              stroke={theme.surface}
              strokeWidth={2}
              // Clickable so a marked regression leads straight to its
              // statistical assessment rather than being decoration.
              onClick={() => onSelectRun?.(point.runId)}
              style={{ cursor: onSelectRun ? "pointer" : "default" }}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: { payload: TrendPoint }[];
  metric: MetricName;
  k: number;
}

function TrendTooltip({ active, payload, metric, k }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  if (!point) return null;

  return (
    <div className="min-w-[13rem] animate-scale-in rounded-md border border-line bg-surface-overlay p-3 shadow-lg">
      <p className="text-label text-ink-tertiary">
        {formatDateTime(point.recordedAt)}
      </p>
      <p className="tnum mt-1.5 text-heading text-ink">
        {formatMetric(point.value)}
        <span className="ml-1.5 text-label font-normal text-ink-tertiary">
          {METRIC_LABELS[metric]}
          {metric === "mrr" ? "" : `@${k}`}
        </span>
      </p>
      <dl className="mt-2.5 space-y-1 border-t border-line-subtle pt-2.5 text-label">
        <div className="flex justify-between gap-4">
          <dt className="text-ink-tertiary">Documents indexed</dt>
          <dd className="tnum text-ink-secondary">{point.documentCount}</dd>
        </div>
        <div className="flex justify-between gap-4">
          <dt className="text-ink-tertiary">Run</dt>
          <dd className="font-mono text-[11px] text-ink-secondary">
            {shortId(point.runId)}
          </dd>
        </div>
      </dl>
      {point.verdict === "degraded" ? (
        <p className="mt-2.5 rounded-sm border border-danger-line bg-danger-subtle px-2 py-1 text-label text-danger-text">
          Regression — click the marker for the assessment
        </p>
      ) : null}
    </div>
  );
}
