import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

export type Tone = "neutral" | "accent" | "success" | "warning" | "danger" | "info";

/**
 * Tinted rather than solid.
 *
 * A solid badge competes with the primary action for attention. These read as
 * metadata, which is what a status chip almost always is.
 */
const TONES: Record<Tone, string> = {
  neutral: "bg-inset text-ink-secondary border-line",
  accent: "bg-accent-subtle text-accent-text border-accent-line",
  success: "bg-success-subtle text-success-text border-success-line",
  warning: "bg-warning-subtle text-warning-text border-warning-line",
  danger: "bg-danger-subtle text-danger-text border-danger-line",
  info: "bg-info-subtle text-info-text border-info-line",
};

interface BadgeProps {
  tone?: Tone;
  children: ReactNode;
  icon?: ReactNode;
  className?: string;
  mono?: boolean;
}

export function Badge({ tone = "neutral", children, icon, className, mono }: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded border px-1.5 py-0.5",
        "text-label whitespace-nowrap",
        mono && "font-mono text-[11px] tracking-tight",
        TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  );
}

/** A monospace chip for ids, fingerprints and document keys. */
export function Code({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <code
      className={cn(
        "rounded-sm border border-line-subtle bg-inset px-1.5 py-0.5",
        "font-mono text-[11px] leading-4 text-ink-secondary",
        className,
      )}
    >
      {children}
    </code>
  );
}
