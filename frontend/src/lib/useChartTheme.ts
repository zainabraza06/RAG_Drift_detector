import { useEffect, useState } from "react";

/**
 * Resolved chart colours.
 *
 * Recharts writes SVG presentation attributes, which do not resolve CSS
 * custom properties, so the tokens have to be read out of the cascade as
 * concrete colours. A MutationObserver on the root class re-reads them the
 * moment the theme flips, which is what keeps the charts in step with the
 * rest of the UI instead of needing a reload.
 */
export interface ChartTheme {
  brand: string;
  grid: string;
  axis: string;
  critical: string;
  warning: string;
  healthy: string;
  surface: string;
  border: string;
}

const TOKENS: Record<keyof ChartTheme, string> = {
  brand: "--brand",
  grid: "--border",
  axis: "--text-subtle",
  critical: "--critical",
  warning: "--warning",
  healthy: "--healthy",
  surface: "--surface-raised",
  border: "--border-strong",
};

function readTheme(): ChartTheme {
  const styles = getComputedStyle(document.documentElement);
  const resolve = (token: string) => `hsl(${styles.getPropertyValue(token).trim()})`;

  return Object.fromEntries(
    Object.entries(TOKENS).map(([key, token]) => [key, resolve(token)]),
  ) as unknown as ChartTheme;
}

export function useChartTheme(): ChartTheme {
  const [theme, setTheme] = useState<ChartTheme>(() => readTheme());

  useEffect(() => {
    const observer = new MutationObserver(() => setTheme(readTheme()));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });

    // The system theme can change without the class attribute moving.
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => setTheme(readTheme());
    media.addEventListener("change", onChange);

    return () => {
      observer.disconnect();
      media.removeEventListener("change", onChange);
    };
  }, []);

  return theme;
}
