import type { CSSProperties } from "react";

import { cn } from "@/lib/cn";

/**
 * Skeletons mirror the shape of what they replace, so the layout does not
 * shift when data arrives. A spinner in a card-shaped hole reflows twice.
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
        "relative overflow-hidden rounded bg-inset",
        "after:absolute after:inset-0 after:animate-shimmer",
        "after:bg-gradient-to-r after:from-transparent after:via-surface/70 after:to-transparent",
        className,
      )}
      aria-hidden
    />
  );
}
