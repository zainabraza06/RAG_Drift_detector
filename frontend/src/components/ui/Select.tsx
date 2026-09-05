import { ChevronDown } from "lucide-react";
import type { SelectHTMLAttributes } from "react";

import { cn } from "@/lib/cn";

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  selectSize?: "sm" | "md";
}

export function Select({
  label,
  selectSize = "md",
  className,
  children,
  ...props
}: SelectProps) {
  return (
    <label className="inline-flex items-center gap-2">
      {label ? <span className="text-label text-ink-tertiary">{label}</span> : null}
      <span className="relative inline-flex">
        <select
          className={cn(
            "appearance-none rounded-md border border-line bg-surface text-ink",
            "transition-colors duration-fast ease-out",
            "hover:border-line-strong hover:bg-surface-hover focus:border-accent",
            selectSize === "sm" ? "h-7 pl-2 pr-7 text-small" : "h-8 pl-2.5 pr-8 text-small",
            className,
          )}
          {...props}
        >
          {children}
        </select>
        <ChevronDown
          className={cn(
            "pointer-events-none absolute top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-tertiary",
            selectSize === "sm" ? "right-1.5" : "right-2",
          )}
          aria-hidden
        />
      </span>
    </label>
  );
}

/** Segmented control for a small set of mutually exclusive options. */
export function SegmentedControl<T extends string | number>({
  options,
  value,
  onChange,
  ariaLabel,
}: {
  options: { value: T; label: string }[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
}) {
  return (
    <div
      role="radiogroup"
      aria-label={ariaLabel}
      className="inline-flex items-center gap-0.5 rounded-md border border-line bg-inset p-0.5"
    >
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={String(option.value)}
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={cn(
              "rounded px-2.5 py-1 text-label transition-colors duration-fast ease-out",
              active
                ? "bg-surface text-ink shadow-xs"
                : "text-ink-tertiary hover:text-ink-secondary",
            )}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
