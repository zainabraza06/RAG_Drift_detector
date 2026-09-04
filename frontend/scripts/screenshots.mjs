/**
 * Captures the README screenshots from a running stack.
 *
 * The screenshots in the README are generated, not hand-edited, so they can be
 * regenerated whenever the UI changes and can never quietly drift out of date.
 *
 *   # 1. give the instance a history worth looking at
 *   cd backend && python -m scripts.seed_demo_history --reset
 *   # 2. start the API and the dev server
 *   python -m app.cli serve &
 *   cd ../frontend && npm run dev &
 *   # 3. capture
 *   npm run screenshots
 *
 * Uses the browser already installed on the machine (`channel: "chrome"`)
 * rather than downloading one.
 */
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";

const BASE = process.env.SHOT_BASE ?? "http://127.0.0.1:5173";
const OUT = process.env.SHOT_OUT ?? "../docs/screenshots";

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: "chrome" });

async function shot(name, path, { theme = "light", width = 1440, height = 940, prepare } = {}) {
  const context = await browser.newContext({
    viewport: { width, height },
    deviceScaleFactor: 2,
    colorScheme: theme === "dark" ? "dark" : "light",
  });
  const page = await context.newPage();

  await page.addInitScript((t) => {
    try {
      localStorage.setItem("drift-theme", t);
    } catch (_) {
      /* ignore */
    }
  }, theme);

  await page.goto(`${BASE}${path}`, { waitUntil: "networkidle" });
  await page.waitForTimeout(1400);
  if (prepare) await prepare(page);
  await page.waitForTimeout(900);

  const file = `${OUT}/${name}.png`;
  await page.screenshot({ path: file, animations: "disabled" });
  console.log(`  captured ${file}`);
  await context.close();
}

console.log("capturing…");

await shot("dashboard", "/");
await shot("dashboard-dark", "/", { theme: "dark" });
await shot("trends", "/trends");
await shot("drift-events", "/drift", {
  height: 1250,
  prepare: async (page) => {
    // Expand the first event so the statistical table and the diagnostics
    // panel are both visible in the capture.
    const first = page.locator('button[aria-expanded]').first();
    if (await first.count()) await first.click();
    await page.waitForTimeout(700);
  },
});
await shot("drift-diagnostics", "/drift", {
  theme: "dark",
  height: 1250,
  prepare: async (page) => {
    const first = page.locator('button[aria-expanded]').first();
    if (await first.count()) await first.click();
    await page.waitForTimeout(700);
    const notice = page.getByText(/heuristics, not statistical findings/i).first();
    if (await notice.count()) await notice.scrollIntoViewIfNeeded();
  },
});
await shot("golden-set", "/golden-set");
await shot("mobile", "/", { width: 420, height: 900 });

await browser.close();
console.log("done");
