import type { CSSProperties } from "react";

import { cn } from "@/lib/cn";

/**
 * A shimmering placeholder.
 *
 * Skeletons mirror the shape of the content they stand in for, so the layout
 * does not jump when data arrives — a spinner in a card-shaped hole reflows
 * the page twice.
 */
export function Skeleton({
  className,
  style,
}: {
  className?: string;
  style?: CSSProperties;
}) {
  return (
    <div
      style={style}
      className={cn(
        "relative overflow-hidden rounded-md bg-surface-muted",
        "after:absolute after:inset-0 after:animate-shimmer",
        "after:bg-gradient-to-r after:from-transparent after:via-line/60 after:to-transparent",
        className,
      )}
      aria-hidden
    />
  );
}
