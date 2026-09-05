import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/cn";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description: ReactNode;
  action?: ReactNode;
  className?: string;
}

/**
 * Always explains *why* it is empty and what to do next. An unexplained empty
 * panel reads as a bug, and gets reported as one.
 */
export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex animate-fade-in flex-col items-center justify-center px-6 py-16 text-center",
        className,
      )}
    >
      <span className="mb-4 grid h-9 w-9 place-items-center rounded-lg border border-line bg-inset">
        <Icon className="h-4 w-4 text-ink-tertiary" aria-hidden />
      </span>
      <h3 className="text-heading text-ink">{title}</h3>
      <p className="mt-1.5 max-w-[38ch] text-body leading-6 text-ink-secondary">
        {description}
      </p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
