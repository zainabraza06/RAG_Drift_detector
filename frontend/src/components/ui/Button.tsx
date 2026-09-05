import { Loader2 } from "lucide-react";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

/**
 * Exactly one variant is filled.
 *
 * A screen with several solid buttons has no primary action. `secondary` is
 * the default precisely so that reaching for `primary` is a deliberate choice
 * about hierarchy.
 */
const VARIANTS: Record<Variant, string> = {
  primary: cn(
    "bg-accent text-accent-fg shadow-xs",
    "hover:bg-accent-hover active:bg-accent-active",
    "disabled:bg-accent/45 disabled:shadow-none",
  ),
  secondary: cn(
    "bg-surface text-ink border border-line shadow-xs",
    "hover:bg-surface-hover hover:border-line-strong",
    "active:bg-inset",
  ),
  ghost: cn(
    "text-ink-secondary",
    "hover:bg-surface-hover hover:text-ink active:bg-inset",
  ),
  danger: cn(
    "bg-danger text-white shadow-xs",
    "hover:bg-danger/90 active:bg-danger/95",
  ),
};

const SIZES: Record<Size, string> = {
  sm: "h-7 gap-1.5 px-2.5 text-label rounded",
  md: "h-8 gap-1.5 px-3 text-small font-medium rounded-md",
  lg: "h-10 gap-2 px-4 text-body font-medium rounded-md",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  icon?: ReactNode;
  iconTrailing?: ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = "secondary",
    size = "md",
    loading,
    icon,
    iconTrailing,
    className,
    children,
    disabled,
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      // A loading button stays disabled so a double click cannot fire two
      // evaluations, each of which would write a run.
      disabled={disabled || loading}
      className={cn(
        "inline-flex shrink-0 select-none items-center justify-center whitespace-nowrap",
        "transition-colors duration-fast ease-out",
        "disabled:pointer-events-none disabled:opacity-55",
        VARIANTS[variant],
        SIZES[size],
        className,
      )}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin" aria-hidden />
      ) : (
        icon
      )}
      {children}
      {iconTrailing}
    </button>
  );
});

/** A square button for a lone icon. Always needs an aria-label. */
export const IconButton = forwardRef<
  HTMLButtonElement,
  Omit<ButtonProps, "children" | "iconTrailing"> & { "aria-label": string }
>(function IconButton({ variant = "ghost", size = "md", className, icon, ...props }, ref) {
  return (
    <Button
      ref={ref}
      variant={variant}
      size={size}
      className={cn(
        "px-0",
        size === "sm" ? "w-7" : size === "md" ? "w-8" : "w-10",
        className,
      )}
      {...props}
    >
      {icon}
    </Button>
  );
});
