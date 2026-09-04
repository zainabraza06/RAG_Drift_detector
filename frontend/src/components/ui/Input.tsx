import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid, className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        "h-9 w-full rounded-lg border bg-surface px-3 text-sm text-content",
        "placeholder:text-content-subtle transition-colors",
        invalid
          ? "border-critical focus:border-critical focus:ring-critical/40"
          : "border-line hover:border-line-strong focus:border-brand",
        className,
      )}
      {...props}
    />
  );
});
