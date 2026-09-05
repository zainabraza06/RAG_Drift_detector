import { useId, useState, type ReactNode } from "react";

import { cn } from "@/lib/cn";

interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  className?: string;
  side?: "top" | "bottom";
}

/**
 * Opens on focus as well as hover and is wired with aria-describedby, so the
 * explanation is reachable without a pointer. Several of these carry the only
 * plain-English statement of what a statistic means, so they are not optional
 * decoration.
 */
export function Tooltip({ content, children, className, side = "top" }: TooltipProps) {
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
            "pointer-events-none absolute left-1/2 z-50 w-max max-w-[19rem] -translate-x-1/2",
            "animate-scale-in rounded-md border border-line bg-surface-overlay",
            "px-2.5 py-1.5 text-small leading-5 text-ink-secondary shadow-lg",
            side === "top" ? "bottom-full mb-2" : "top-full mt-2",
          )}
        >
          {content}
        </span>
      ) : null}
    </span>
  );
}

/** Marks a term that carries a tooltip, without shouting. */
export function Explained({
  content,
  children,
}: {
  content: ReactNode;
  children: ReactNode;
}) {
  return (
    <Tooltip content={content}>
      <span className="cursor-help decoration-line-strong decoration-dotted underline-offset-4 [text-decoration-line:underline]">
        {children}
      </span>
    </Tooltip>
  );
}
