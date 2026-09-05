import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  invalid?: boolean;
  inputSize?: "sm" | "md";
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { invalid, inputSize = "md", className, ...props },
  ref,
) {
  return (
    <input
      ref={ref}
      aria-invalid={invalid || undefined}
      className={cn(
        "w-full rounded-md border bg-surface text-ink",
        "placeholder:text-ink-disabled",
        "transition-colors duration-fast ease-out",
        inputSize === "sm" ? "h-7 px-2 text-small" : "h-8 px-2.5 text-body",
        invalid
          ? "border-danger-line bg-danger-subtle/40"
          : "border-line hover:border-line-strong focus:border-accent",
        className,
      )}
      {...props}
    />
  );
});

/** Label + field + optional error, with the spacing already decided. */
export function Field({
  label,
  hint,
  error,
  children,
}: {
  label?: string;
  hint?: string;
  error?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      {label ? <div className="text-label text-ink-secondary">{label}</div> : null}
      {children}
      {error ? (
        <p className="text-label text-danger-text">{error}</p>
      ) : hint ? (
        <p className="text-label text-ink-tertiary">{hint}</p>
      ) : null}
    </div>
  );
}
