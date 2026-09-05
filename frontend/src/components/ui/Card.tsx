import type { HTMLAttributes, ReactNode } from "react";

import { cn } from "@/lib/cn";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** Adds a hover affordance. Only for cards that are entirely clickable. */
  interactive?: boolean;
  /** Removes the border and shadow, for cards nested inside another surface. */
  flush?: boolean;
}

/**
 * The one container primitive.
 *
 * A hairline border and a single-step surface lift do the work; the shadow is
 * almost imperceptible and exists only to soften the edge. Stacking heavier
 * shadows to imply depth is the fastest way to make an interface look
 * generic, so elevation here is carried by the border.
 */
export function Card({ interactive, flush, className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-lg bg-surface",
        !flush && "border border-line shadow-xs",
        interactive &&
          "cursor-pointer transition-colors duration-fast ease-out hover:border-line-strong hover:bg-surface-hover",
        className,
      )}
      {...props}
    />
  );
}

interface CardHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
  /** Drops the bottom rule when the body supplies its own separation. */
  bare?: boolean;
}

export function CardHeader({
  title,
  description,
  action,
  className,
  bare,
}: CardHeaderProps) {
  return (
    <div
      className={cn(
        "flex items-start justify-between gap-4 px-5 py-4",
        !bare && "border-b border-line-subtle",
        className,
      )}
    >
      <div className="min-w-0">
        <h2 className="truncate text-heading text-ink">{title}</h2>
        {description ? (
          <p className="mt-1 text-small text-ink-tertiary">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function CardBody({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("px-5 py-4", className)} {...props} />;
}

export function CardFooter({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "border-t border-line-subtle bg-inset/50 px-5 py-3",
        className,
      )}
      {...props}
    />
  );
}

/** A labelled section heading used above a group of cards. */
export function SectionHeading({
  children,
  action,
}: {
  children: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-3 flex items-end justify-between gap-4">
      <h2 className="text-micro uppercase text-ink-tertiary">{children}</h2>
      {action}
    </div>
  );
}
