// Capture README screenshots and demo-GIF frames from a locally running dashboard.
//
// Prerequisites: API on :8000 and dashboard on :3000 with some demo data, Google Chrome,
// and `npm install playwright-core` in a scratch folder.
// usage: node capture-screenshots.js <en|ko> <outDir> [--gif]
// Frames in <outDir>/frames are named NNN_<hold>.png; <hold> is the frame duration in ticks.
const { chromium } = require("playwright-core");
const fs = require("fs");
const path = require("path");

const [lang, outDir, gifFlag] = process.argv.slice(2);
const BASE = "http://localhost:3000";
fs.mkdirSync(outDir, { recursive: true });

async function settle(page) {
  await page.waitForLoadState("networkidle");
  await page.waitForTimeout(600);
}

(async () => {
  const browser = await chromium.launch({ channel: "chrome", headless: true });
  const ctx = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    locale: lang === "ko" ? "ko-KR" : "en-US",
  });
  const page = await ctx.newPage();

  // 1) dashboard — hero (top of page) + full page
  await page.goto(`${BASE}/?lang=${lang}`);
  await settle(page);
  await page.screenshot({ path: path.join(outDir, `dashboard-${lang}.png`), clip: { x: 0, y: 0, width: 1440, height: 1500 }, fullPage: true });
  await page.screenshot({ path: path.join(outDir, `dashboard-full-${lang}.png`), fullPage: true });

  // 2) scenarios — run one and capture the four-phase trace
  await page.goto(`${BASE}/scenarios?lang=${lang}`);
  await settle(page);
  await page.screenshot({ path: path.join(outDir, `scenarios-${lang}.png`), clip: { x: 0, y: 0, width: 1440, height: 1100 }, fullPage: true });
  const card = page.locator(".card", { hasText: lang === "ko" ? "분기 포트폴리오 통합 리뷰" : "Quarterly portfolio review" }).first();
  await card.click();
  await page.waitForSelector("text=" + (lang === "ko" ? "인사이트 —" : "Insight —"));
  await settle(page);
  const trace = page.locator(".card", { has: page.locator("pre, table, ul") }).last();
  await trace.scrollIntoViewIfNeeded();
  await trace.screenshot({ path: path.join(outDir, `scenario-trace-${lang}.png`) });

  // 3) approvals (HITL)
  await page.goto(`${BASE}/approvals?lang=${lang}`);
  await settle(page);
  await page.screenshot({ path: path.join(outDir, `approvals-${lang}.png`), clip: { x: 0, y: 0, width: 1440, height: 1100 }, fullPage: true });

  await ctx.close();

  // 4) GIF frames (1x scale, smaller viewport)
  if (gifFlag === "--gif") {
    const framesDir = path.join(outDir, "frames");
    fs.mkdirSync(framesDir, { recursive: true });
    const g = await browser.newContext({ viewport: { width: 1280, height: 760 }, deviceScaleFactor: 1 });
    const p = await g.newPage();
    let n = 0;
    const snap = async (hold = 1) => {
      const f = path.join(framesDir, `${String(n++).padStart(3, "0")}_${hold}.png`);
      await p.screenshot({ path: f });
    };
    const scroll = async (y, steps = 4) => {
      const start = await p.evaluate(() => window.scrollY);
      for (let i = 1; i <= steps; i++) {
        await p.evaluate((v) => window.scrollTo(0, v), start + ((y - start) * i) / steps);
        await p.waitForTimeout(80);
        await snap(i === steps ? 6 : 1);
      }
    };

    await p.goto(`${BASE}/?lang=en`);
    await p.waitForLoadState("networkidle"); await p.waitForTimeout(500);
    await snap(14);
    await scroll(560); await scroll(1150); await scroll(1800);

    await p.goto(`${BASE}/scenarios?lang=en`);
    await p.waitForLoadState("networkidle"); await p.waitForTimeout(400);
    await snap(10);
    await p.locator(".card", { hasText: "Risk early warning" }).first().click();
    await p.waitForSelector("text=Insight —"); await p.waitForTimeout(400);
    const y = await p.evaluate(() => {
      const cards = [...document.querySelectorAll(".card")];
      return cards[cards.length - 1].getBoundingClientRect().top + window.scrollY - 20;
    });
    await scroll(y, 6);
    await scroll(y + 520, 4);

    // switch language with the toggle
    await p.evaluate(() => window.scrollTo(0, 0)); await p.waitForTimeout(150);
    await snap(6);
    await p.locator(".lang-switch button", { hasText: "한국어" }).click();
    await p.waitForLoadState("networkidle"); await p.waitForTimeout(600);
    await snap(14);

    await p.goto(`${BASE}/approvals`);
    await p.waitForLoadState("networkidle"); await p.waitForTimeout(500);
    await snap(14);
    await g.close();
  }
  await browser.close();
  console.log("done", lang);
})().catch((e) => { console.error(e); process.exit(1); });
