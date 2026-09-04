import { cn } from "@/lib/cn";
import { HEALTH_META } from "@/lib/display";
import type { HealthStatus } from "@/lib/types";

interface HealthBadgeProps {
  status: HealthStatus;
  size?: "sm" | "md";
  className?: string;
}

export function HealthBadge({ status, size = "md", className }: HealthBadgeProps) {
  const meta = HEALTH_META[status];
  const Icon = meta.icon;

  return (
    <span
      title={meta.hint}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-medium ring-1 ring-inset",
        size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-sm",
        meta.chip,
        className,
      )}
    >
      <Icon className={size === "sm" ? "h-3 w-3" : "h-3.5 w-3.5"} aria-hidden />
      {meta.label}
    </span>
  );
}

/** A pulsing dot, for the header where the label would be redundant. */
export function HealthDot({ status }: { status: HealthStatus }) {
  const meta = HEALTH_META[status];
  return (
    <span className="relative inline-flex h-2.5 w-2.5 shrink-0" title={meta.hint}>
      {status === "critical" ? (
        <span
          className={cn("absolute inset-0 rounded-full animate-pulse-ring", meta.dot)}
          aria-hidden
        />
      ) : null}
      <span className={cn("relative h-2.5 w-2.5 rounded-full", meta.dot)} />
    </span>
  );
}
