import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type Tone = "neutral" | "brand" | "healthy" | "warning" | "critical";

const TONES: Record<Tone, string> = {
  neutral: "bg-unknown-soft text-content-muted ring-unknown/20",
  brand: "bg-brand-soft text-brand ring-brand/20",
  healthy: "bg-healthy-soft text-healthy ring-healthy/25",
  warning: "bg-warning-soft text-warning ring-warning/25",
  critical: "bg-critical-soft text-critical ring-critical/25",
};

interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  icon?: ReactNode;
  className?: string;
  /** Renders in a monospace face; use for ids and fingerprints. */
  mono?: boolean;
}

export function Badge({ tone = "neutral", children, icon, className, mono }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
        mono && "font-mono text-2xs tracking-tight",
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}
