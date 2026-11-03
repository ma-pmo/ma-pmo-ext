// Capture README screenshots and demo-GIF frames from a locally running dashboard.
//
// Prerequisites: API and dashboard running with demo data (`make db-init`, `make api`, `make web`),
// Google Chrome, and `npm install playwright-core` in a scratch folder.
// usage: node capture-screenshots.js <outDir> [--gif] [--base http://localhost:3000]
// Writes <page>-<en|ko>.png for dashboard, scenarios, scenario-trace, approvals, evaluation and
// integrations (1440x900 @2x, light theme). With --gif, frames go to <outDir>/frames named
// NNN_<hold>.png, where <hold> is the frame duration in ticks.
const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const args = process.argv.slice(2);
const outDir = args[0];
const gif = args.includes("--gif");
const BASE = args.includes("--base") ? args[args.indexOf("--base") + 1] : "http://localhost:3000";
if (!outDir) {
  console.error("usage: node capture-screenshots.js <outDir> [--gif] [--base URL]");
  process.exit(2);
}
fs.mkdirSync(outDir, { recursive: true });

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });

  // 1) one screenshot per page and language
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "light" });
  const page = await ctx.newPage();
  const go = async (route, lang) => {
    await page.goto(`${BASE}${route}?lang=${lang}`);
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(600);
  };
  const shot = (name) => page.screenshot({ path: path.join(outDir, name) });

  for (const lang of ["en", "ko"]) {
    await go("/", lang); await shot(`dashboard-${lang}.png`);
    await go("/scenarios", lang); await shot(`scenarios-${lang}.png`);
    const title = lang === "ko" ? "분기 포트폴리오 통합 리뷰" : "Quarterly portfolio review";
    await page.locator(".card", { hasText: title }).locator("button").click();
    await page.waitForSelector(lang === "ko" ? "text=인사이트 —" : "text=Insight —");
    await page.waitForTimeout(900); await shot(`scenario-trace-${lang}.png`);
    await go("/approvals", lang); await shot(`approvals-${lang}.png`);
    await go("/evaluation", lang); await shot(`evaluation-${lang}.png`);
    await go("/integrations", lang); await shot(`integrations-${lang}.png`);
  }
  await ctx.close();

  // 2) GIF frames (1x scale, smaller viewport): dashboard → scenario run → approve → evaluation → Korean
  if (gif) {
    const framesDir = path.join(outDir, "frames");
    fs.mkdirSync(framesDir, { recursive: true });
    const g = await browser.newContext({ viewport: { width: 1280, height: 760 }, deviceScaleFactor: 1, locale: "en-US" });
    const p = await g.newPage();
    let n = 0;
    const snap = (hold = 1) => p.screenshot({ path: path.join(framesDir, `${String(n++).padStart(3, "0")}_${hold}.png`) });
    const scroll = async (y, steps = 4) => {
      const start = await p.evaluate(() => window.scrollY);
      for (let i = 1; i <= steps; i++) {
        await p.evaluate((v) => window.scrollTo(0, v), start + ((y - start) * i) / steps);
        await p.waitForTimeout(80);
        await snap(i === steps ? 6 : 1);
      }
    };
    const nav = async (label, wait = 500) => {
      await p.locator(".nav-item", { hasText: label }).click();
      await p.waitForLoadState("networkidle"); await p.waitForTimeout(wait);
    };

    await p.goto(`${BASE}/?lang=en`); await p.waitForLoadState("networkidle"); await p.waitForTimeout(600);
    await snap(14); await scroll(520); await scroll(1100);
    await nav("Scenarios"); await snap(8);
    await p.locator(".card", { hasText: "Risk early warning" }).locator("button").click();
    await p.waitForSelector("text=Insight —"); await p.waitForTimeout(900);
    await snap(10); await scroll(await p.evaluate(() => window.scrollY + 480), 4);
    await nav("Approvals"); await snap(10);
    await p.locator("tbody tr").first().locator("button", { hasText: "Approve" }).click(); await p.waitForTimeout(700);
    await snap(8);
    await nav("Evaluation", 700); await snap(14);
    await p.locator(".topbar button", { hasText: "한국어" }).click();
    await p.waitForLoadState("networkidle"); await p.waitForTimeout(900);
    await snap(14);
    await nav("연동", 600); await snap(12);
    await g.close();
  }

  await browser.close();
  console.log(`saved to ${outDir}`);
})().catch((e) => { console.error(e); process.exit(1); });
