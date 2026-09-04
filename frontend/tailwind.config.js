/**
 * Design tokens.
 *
 * Every colour is a CSS custom property holding a bare HSL triplet, so a
 * single `<html class="dark">` swap re-themes the whole application and
 * Tailwind's opacity modifiers (`bg-surface/60`) still work. Components refer
 * to semantic names — `surface`, `border`, `critical` — never to a raw palette
 * step, so the theme can change without touching a component.
 */
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "hsl(var(--canvas) / <alpha-value>)",
        surface: {
          DEFAULT: "hsl(var(--surface) / <alpha-value>)",
          muted: "hsl(var(--surface-muted) / <alpha-value>)",
          raised: "hsl(var(--surface-raised) / <alpha-value>)",
        },
        line: {
          DEFAULT: "hsl(var(--border) / <alpha-value>)",
          strong: "hsl(var(--border-strong) / <alpha-value>)",
        },
        content: {
          DEFAULT: "hsl(var(--text) / <alpha-value>)",
          muted: "hsl(var(--text-muted) / <alpha-value>)",
          subtle: "hsl(var(--text-subtle) / <alpha-value>)",
        },
        brand: {
          DEFAULT: "hsl(var(--brand) / <alpha-value>)",
          soft: "hsl(var(--brand-soft) / <alpha-value>)",
          fg: "hsl(var(--brand-fg) / <alpha-value>)",
        },
        healthy: {
          DEFAULT: "hsl(var(--healthy) / <alpha-value>)",
          soft: "hsl(var(--healthy-soft) / <alpha-value>)",
        },
        warning: {
          DEFAULT: "hsl(var(--warning) / <alpha-value>)",
          soft: "hsl(var(--warning-soft) / <alpha-value>)",
        },
        critical: {
          DEFAULT: "hsl(var(--critical) / <alpha-value>)",
          soft: "hsl(var(--critical-soft) / <alpha-value>)",
        },
        unknown: {
          DEFAULT: "hsl(var(--unknown) / <alpha-value>)",
          soft: "hsl(var(--unknown-soft) / <alpha-value>)",
        },
      },
      fontFamily: {
        sans: [
          "Inter var",
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: [
          "ui-monospace",
          "SFMono-Regular",
          "SF Mono",
          "Menlo",
          "Consolas",
          "Liberation Mono",
          "monospace",
        ],
      },
      // A restrained type scale: five sizes cover the whole application, with
      // line-height and tracking tuned per step rather than left to defaults.
      fontSize: {
        "2xs": ["0.6875rem", { lineHeight: "1rem", letterSpacing: "0.02em" }],
        xs: ["0.75rem", { lineHeight: "1.125rem", letterSpacing: "0.01em" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.875rem", { lineHeight: "1.5rem" }],
        lg: ["1rem", { lineHeight: "1.6rem" }],
        xl: ["1.25rem", { lineHeight: "1.75rem", letterSpacing: "-0.01em" }],
        "2xl": ["1.5rem", { lineHeight: "2rem", letterSpacing: "-0.018em" }],
        "3xl": ["1.875rem", { lineHeight: "2.25rem", letterSpacing: "-0.022em" }],
        stat: ["2rem", { lineHeight: "2.25rem", letterSpacing: "-0.028em" }],
      },
      borderRadius: {
        lg: "0.625rem",
        xl: "0.875rem",
        "2xl": "1.125rem",
      },
      boxShadow: {
        // Shadows are near-invisible on a dark canvas, so elevation is carried
        // by borders there; these stay subtle enough not to fight either theme.
        card: "0 1px 2px 0 hsl(var(--shadow) / 0.04), 0 1px 3px 0 hsl(var(--shadow) / 0.06)",
        raised:
          "0 2px 4px -1px hsl(var(--shadow) / 0.06), 0 8px 16px -4px hsl(var(--shadow) / 0.08)",
        popover:
          "0 4px 8px -2px hsl(var(--shadow) / 0.08), 0 16px 32px -8px hsl(var(--shadow) / 0.14)",
      },
      keyframes: {
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.97)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "pulse-ring": {
          "0%": { transform: "scale(0.9)", opacity: "0.7" },
          "70%": { transform: "scale(1.6)", opacity: "0" },
          "100%": { transform: "scale(1.6)", opacity: "0" },
        },
      },
      animation: {
        "fade-in": "fade-in 180ms ease-out",
        "fade-up": "fade-up 260ms cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-in": "scale-in 160ms cubic-bezier(0.16, 1, 0.3, 1)",
        shimmer: "shimmer 1.6s infinite",
        "pulse-ring": "pulse-ring 2.4s cubic-bezier(0.24, 0, 0.38, 1) infinite",
      },
    },
  },
  plugins: [],
};
