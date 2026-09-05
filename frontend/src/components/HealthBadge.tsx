import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import { HEALTH_META } from "@/lib/display";
import type { HealthStatus } from "@/lib/types";

export function HealthBadge({
  status,
  className,
}: {
  status: HealthStatus;
  className?: string;
}) {
  const meta = HEALTH_META[status];
  const Icon = meta.icon;

  return (
    <Badge
      tone={meta.tone}
      className={className}
      icon={<Icon className="h-3 w-3" aria-hidden />}
    >
      {meta.label}
    </Badge>
  );
}

/**
 * A status dot for the header, where a full chip would be noise.
 *
 * Only the state that needs attention animates. A dashboard where everything
 * pulses teaches people to ignore the one thing that matters.
 */
export function HealthDot({ status }: { status: HealthStatus }) {
  const meta = HEALTH_META[status];
  return (
    <span
      className="relative inline-flex h-2 w-2 shrink-0"
      title={meta.hint}
      aria-label={meta.label}
    >
      <span
        className={cn(
          "h-2 w-2 rounded-full",
          meta.solid,
          status === "critical" && "animate-pulse-soft",
        )}
      />
    </span>
  );
}
