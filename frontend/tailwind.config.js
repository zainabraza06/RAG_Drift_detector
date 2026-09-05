/**
 * Tailwind is configured to expose the semantic tokens in `index.css` and
 * almost nothing else. A component can say `bg-surface` or `text-ink-secondary`
 * but has no way to reach for `slate-700`, which is what keeps the system
 * coherent as it grows.
 *
 * Every colour is a bare HSL triplet so opacity modifiers (`bg-accent/10`)
 * still work, and so one class on <html> re-themes the whole application.
 */
/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    // The default palette is replaced rather than extended: `bg-red-500` is a
    // mistake in this codebase, and it should not compile.
    colors: {
      transparent: "transparent",
      current: "currentColor",
      inherit: "inherit",
      white: "#fff",
      black: "#000",

      app: "hsl(var(--bg-app) / <alpha-value>)",
      surface: {
        DEFAULT: "hsl(var(--bg-surface) / <alpha-value>)",
        hover: "hsl(var(--bg-surface-hover) / <alpha-value>)",
        inset: "hsl(var(--bg-inset) / <alpha-value>)",
        overlay: "hsl(var(--bg-overlay) / <alpha-value>)",
      },
      line: {
        subtle: "hsl(var(--line-subtle) / <alpha-value>)",
        DEFAULT: "hsl(var(--line) / <alpha-value>)",
        strong: "hsl(var(--line-strong) / <alpha-value>)",
      },
      ink: {
        DEFAULT: "hsl(var(--ink) / <alpha-value>)",
        secondary: "hsl(var(--ink-secondary) / <alpha-value>)",
        tertiary: "hsl(var(--ink-tertiary) / <alpha-value>)",
        disabled: "hsl(var(--ink-disabled) / <alpha-value>)",
      },
      accent: {
        DEFAULT: "hsl(var(--accent) / <alpha-value>)",
        hover: "hsl(var(--accent-hover) / <alpha-value>)",
        active: "hsl(var(--accent-active) / <alpha-value>)",
        fg: "hsl(var(--accent-fg) / <alpha-value>)",
        text: "hsl(var(--accent-text) / <alpha-value>)",
        subtle: "hsl(var(--accent-subtle) / <alpha-value>)",
        line: "hsl(var(--accent-line) / <alpha-value>)",
      },
      success: {
        DEFAULT: "hsl(var(--success) / <alpha-value>)",
        text: "hsl(var(--success-text) / <alpha-value>)",
        subtle: "hsl(var(--success-subtle) / <alpha-value>)",
        line: "hsl(var(--success-line) / <alpha-value>)",
      },
      warning: {
        DEFAULT: "hsl(var(--warning) / <alpha-value>)",
        text: "hsl(var(--warning-text) / <alpha-value>)",
        subtle: "hsl(var(--warning-subtle) / <alpha-value>)",
        line: "hsl(var(--warning-line) / <alpha-value>)",
      },
      danger: {
        DEFAULT: "hsl(var(--danger) / <alpha-value>)",
        text: "hsl(var(--danger-text) / <alpha-value>)",
        subtle: "hsl(var(--danger-subtle) / <alpha-value>)",
        line: "hsl(var(--danger-line) / <alpha-value>)",
      },
      info: {
        DEFAULT: "hsl(var(--info) / <alpha-value>)",
        text: "hsl(var(--info-text) / <alpha-value>)",
        subtle: "hsl(var(--info-subtle) / <alpha-value>)",
        line: "hsl(var(--info-line) / <alpha-value>)",
      },
    },

    // A strict 4px rhythm. Tailwind's default scale already steps in 4px
    // units; the odd values are removed so nothing lands off-grid.
    spacing: {
      0: "0px",
      px: "1px",
      0.5: "2px",
      1: "4px",
      1.5: "6px",
      2: "8px",
      2.5: "10px",
      3: "12px",
      4: "16px",
      5: "20px",
      6: "24px",
      7: "28px",
      8: "32px",
      9: "36px",
      10: "40px",
      11: "44px",
      12: "48px",
      14: "56px",
      16: "64px",
      20: "80px",
      24: "96px",
      32: "128px",
      40: "160px",
      48: "192px",
      56: "224px",
      64: "256px",
    },

    extend: {
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

      /*
       * Seven roles, named for what they are rather than how big they are.
       * Hierarchy comes from size and weight; colour is not load-bearing, so
       * the page still reads correctly in greyscale.
       */
      fontSize: {
        display: ["30px", { lineHeight: "36px", letterSpacing: "-0.021em", fontWeight: "600" }],
        title: ["22px", { lineHeight: "28px", letterSpacing: "-0.018em", fontWeight: "600" }],
        heading: ["16px", { lineHeight: "24px", letterSpacing: "-0.011em", fontWeight: "600" }],
        subheading: ["14px", { lineHeight: "20px", letterSpacing: "-0.006em", fontWeight: "600" }],
        body: ["14px", { lineHeight: "22px", letterSpacing: "-0.003em" }],
        small: ["13px", { lineHeight: "20px", letterSpacing: "0" }],
        label: ["12px", { lineHeight: "16px", letterSpacing: "0.004em", fontWeight: "500" }],
        micro: ["11px", { lineHeight: "16px", letterSpacing: "0.05em", fontWeight: "600" }],
        // The one oversized role, for headline metrics only.
        metric: ["28px", { lineHeight: "34px", letterSpacing: "-0.024em", fontWeight: "600" }],
      },

      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
        lg: "10px",
        xl: "12px",
        "2xl": "16px",
      },

      /*
       * Shadows are deliberately near-invisible. Elevation is communicated by
       * the border and the surface step; a shadow only softens the boundary of
       * something genuinely floating.
       */
      boxShadow: {
        xs: "0 1px 2px 0 hsl(var(--shadow-color) / 0.04)",
        sm: "0 1px 3px 0 hsl(var(--shadow-color) / 0.06), 0 1px 2px -1px hsl(var(--shadow-color) / 0.04)",
        md: "0 4px 12px -2px hsl(var(--shadow-color) / 0.08), 0 2px 4px -2px hsl(var(--shadow-color) / 0.04)",
        lg: "0 12px 28px -6px hsl(var(--shadow-color) / 0.14), 0 4px 8px -4px hsl(var(--shadow-color) / 0.06)",
        none: "none",
      },

      transitionTimingFunction: {
        // A gentle overshoot-free curve; everything uses one easing so motion
        // feels like it comes from a single system.
        out: "cubic-bezier(0.16, 1, 0.3, 1)",
      },
      transitionDuration: {
        fast: "120ms",
        DEFAULT: "160ms",
        slow: "240ms",
      },

      keyframes: {
        "fade-in": { from: { opacity: "0" }, to: { opacity: "1" } },
        "fade-up": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "scale(0.98)" },
          to: { opacity: "1", transform: "scale(1)" },
        },
        shimmer: { "100%": { transform: "translateX(100%)" } },
        "pulse-soft": {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.45" },
        },
      },
      animation: {
        "fade-in": "fade-in 160ms cubic-bezier(0.16, 1, 0.3, 1)",
        "fade-up": "fade-up 220ms cubic-bezier(0.16, 1, 0.3, 1)",
        "scale-in": "scale-in 140ms cubic-bezier(0.16, 1, 0.3, 1)",
        shimmer: "shimmer 1.8s infinite",
        "pulse-soft": "pulse-soft 2.4s ease-in-out infinite",
      },

      maxWidth: {
        prose: "68ch",
        content: "1400px",
      },
    },
  },
  plugins: [],
};
