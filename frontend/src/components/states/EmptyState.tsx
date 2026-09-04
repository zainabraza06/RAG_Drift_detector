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
 * A designed "nothing here yet".
 *
 * Always explains *why* it is empty and what to do next. An empty panel with
 * no explanation reads as a bug, and users report it as one.
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
        "flex animate-fade-in flex-col items-center justify-center px-6 py-14 text-center",
        className,
      )}
    >
      <span className="mb-4 grid h-12 w-12 place-items-center rounded-xl border border-line bg-surface-muted">
        <Icon className="h-5 w-5 text-content-subtle" aria-hidden />
      </span>
      <h3 className="text-base font-semibold text-content">{title}</h3>
      <p className="mt-1.5 max-w-sm text-sm leading-relaxed text-content-muted">
        {description}
      </p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}
