import { useId, useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  className?: string;
}

/**
 * A small hover/focus tooltip.
 *
 * Opens on focus as well as hover, and is wired up with aria-describedby, so
 * the explanation is reachable without a pointer.
 */
export function Tooltip({ content, children, className }: TooltipProps) {
  const [open, setOpen] = useState(false);
  const id = useId();

  return (
    <span
      className={cn("relative inline-flex", className)}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span aria-describedby={open ? id : undefined} tabIndex={0} className="inline-flex">
        {children}
      </span>
      {open ? (
        <span
          role="tooltip"
          id={id}
          className={cn(
            "pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-max max-w-xs",
            "-translate-x-1/2 animate-scale-in rounded-lg border border-line",
            "bg-surface-raised px-2.5 py-1.5 text-xs leading-relaxed text-content shadow-popover",
          )}
        >
          {content}
        </span>
      ) : null}
    </span>
  );
}
