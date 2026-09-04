/**
 * Presentation helpers.
 *
 * Metric values are shown to three decimals and deltas in *points* rather than
 * percent, because "recall fell 4.2 points" is unambiguous where "recall fell
 * 4.2%" is not — a reader cannot tell an absolute change from a relative one.
 */

const metricFormatter = new Intl.NumberFormat("en", {
  minimumFractionDigits: 3,
  maximumFractionDigits: 3,
});

/** A metric in [0, 1], e.g. `0.933`. */
export function formatMetric(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return metricFormatter.format(value);
}

/** An absolute change expressed in points, e.g. `+1.7 pts`. */
export function formatDelta(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const points = value * 100;
  if (Math.abs(points) < 0.05) return "no change";
  return `${points > 0 ? "+" : "−"}${Math.abs(points).toFixed(1)} pts`;
}

/** A confidence interval, e.g. `[−0.362, −0.086]`. */
export function formatInterval(lower: number, upper: number): string {
  const sign = (value: number) => (value < 0 ? "−" : "+");
  return `[${sign(lower)}${Math.abs(lower).toFixed(3)}, ${sign(upper)}${Math.abs(upper).toFixed(3)}]`;
}

/**
 * A p-value. Below the Monte Carlo floor it is shown as a bound rather than a
 * misleadingly precise figure the resample count cannot support.
 */
export function formatPValue(value: number): string {
  if (value < 0.0001) return "p < 0.0001";
  return `p = ${value.toFixed(4)}`;
}

export function formatPercent(value: number, digits = 0): string {
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatInteger(value: number): string {
  return new Intl.NumberFormat("en").format(value);
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  return `${Math.floor(ms / 60_000)}m ${Math.round((ms % 60_000) / 1000)}s`;
}

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

const timeFormatter = new Intl.DateTimeFormat(undefined, {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

export function formatDateTime(iso: string): string {
  return dateTimeFormatter.format(new Date(iso));
}

export function formatChartTime(iso: string): string {
  return timeFormatter.format(new Date(iso));
}

/** "3 minutes ago", for timestamps a reader scans rather than reads. */
export function formatRelative(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  const relative = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });

  const steps: [Intl.RelativeTimeFormatUnit, number][] = [
    ["second", 60],
    ["minute", 60],
    ["hour", 24],
    ["day", 7],
    ["week", 4.35],
    ["month", 12],
  ];

  let value = seconds;
  for (const [unit, size] of steps) {
    if (Math.abs(value) < size) return relative.format(-Math.round(value), unit);
    value /= size;
  }
  return relative.format(-Math.round(value), "year");
}

/** Short run identifier for dense tables. */
export function shortId(runId: string): string {
  return runId.slice(0, 8);
}
