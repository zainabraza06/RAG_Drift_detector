import { ChevronDown } from "lucide-react";
import type { SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
}

export function Select({ label, className, children, ...props }: SelectProps) {
  return (
    <label className="inline-flex items-center gap-2">
      {label ? (
        <span className="text-xs font-medium text-content-muted">{label}</span>
      ) : null}
      <span className="relative inline-flex">
        <select
          className={cn(
            "h-8 appearance-none rounded-lg border border-line bg-surface pl-3 pr-8",
            "text-xs font-medium text-content transition-colors",
            "hover:border-line-strong focus:border-brand",
            className,
          )}
          {...props}
        >
          {children}
        </select>
        <ChevronDown
          className="pointer-events-none absolute right-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-content-subtle"
          aria-hidden
        />
      </span>
    </label>
  );
}
