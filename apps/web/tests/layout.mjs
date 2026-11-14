// Layout check: opens every dashboard page at several screen sizes, in both languages and both
// themes, and reports what a person would trip over, to the pixel:
//   page-overflow  the page scrolls sideways
//   offscreen      an element sticks out of the screen (outside a sideways-scrolling box)
//   spill          content sticks out of its card
//   clipped        text cut off without an ellipsis, by itself or by a box around it
//   scroll-x       a box other than a table or a graph that scrolls sideways
//   overlap        two controls (links, buttons, fields) on top of each other
//   small-target   a control smaller than 24 x 24 px on a touch screen (WCAG 2.2, 2.5.8)
//   tiny-text      text smaller than 11 px
//   console        an error in the browser console
//
// Needs the API with demo data and the dashboard running, and Google Chrome:
//   node tests/layout.mjs [--base http://localhost:3000] [--api http://localhost:8000]
//                         [--out report.json] [--quick]
// Exits 1 when it finds anything. --quick checks one language and the light theme only.
import { writeFileSync } from "node:fs";
import { chromium } from "playwright-core";

const arg = (name, fallback) => {
  const i = process.argv.indexOf(name);
  return i > 0 ? process.argv[i + 1] : fallback;
};
const BASE = arg("--base", "http://localhost:3000");
const API = arg("--api", "http://localhost:8000");
const OUT = arg("--out", "");
const QUICK = process.argv.includes("--quick");

const SIZES = [
  { name: "phone", width: 375, height: 812, touch: true },
  { name: "tablet", width: 768, height: 1024, touch: true },
  { name: "laptop", width: 1280, height: 800, touch: false },
  { name: "desktop", width: 1440, height: 900, touch: false },
];
const LANGS = QUICK ? ["ko"] : ["en", "ko"];
const THEMES = QUICK ? ["light"] : ["light", "dark"];

async function pages() {
  const runs = await (await fetch(`${API}/runs?workflow=risk_escalation&limit=1`)).json();
  const run = runs[0]?.run_id;
  return [
    { name: "dashboard", path: "/" },
    { name: "scenarios", path: "/scenarios" },
    { name: "scenario-trace", path: "/scenarios", open: "trace" },
    { name: "workflows", path: "/workflows?id=risk_escalation" },
    ...(run ? [{ name: "workflow-run", path: `/workflows?id=risk_escalation&run=${run}` }] : []),
    { name: "workflow-editor", path: "/workflows?id=risk_escalation", open: "editor" },
    { name: "approvals", path: "/approvals" },
    { name: "evaluation", path: "/evaluation" },
    { name: "costs", path: "/costs" },
    { name: "integrations", path: "/integrations" },
    { name: "menu", path: "/", open: "menu" },
  ];
}

// Runs inside the page. Returns the problems it sees.
function inspect({ touch }) {
  const W = window.innerWidth;
  const found = [];
  const path = (el) => {
    const parts = [];
    for (let e = el; e && e !== document.body && parts.length < 4; e = e.parentElement) {
      const cls = [...e.classList].slice(0, 2).map((c) => `.${c}`).join("");
      parts.unshift(`${e.tagName.toLowerCase()}${cls}`);
    }
    return parts.join(" > ");
  };
  const text = (el) => (el.innerText || el.getAttribute("aria-label") || el.value || "").trim().slice(0, 50);
  const shown = (el) => {
    const s = getComputedStyle(el);
    if (s.display === "none" || s.visibility === "hidden" || Number(s.opacity) === 0) return false;
    const r = el.getBoundingClientRect();
    return r.width > 1 && r.height > 1;  // 1 px boxes are screen-reader-only text
  };
  // the closed phone menu sits off screen on purpose
  const hiddenMenu = (el) => {
    const side = el.closest(".sidebar");
    return side && !side.classList.contains("open") && W <= 960;
  };
  const scroller = (el) => {
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      const ox = getComputedStyle(p).overflowX;
      if ((ox === "auto" || ox === "scroll") && p.scrollWidth > p.clientWidth + 1) return p;
    }
    return null;
  };
  const all = [...document.body.querySelectorAll("*")].filter((el) => shown(el) && !hiddenMenu(el));
  // the part of an element its clipping boxes let through
  const visible = (el) => {
    let r = el.getBoundingClientRect();
    let { left, right, top, bottom } = r;
    for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
      if (getComputedStyle(p).overflowX === "visible" && getComputedStyle(p).overflowY === "visible") continue;
      const q = p.getBoundingClientRect();
      left = Math.max(left, q.left); right = Math.min(right, q.right);
      top = Math.max(top, q.top); bottom = Math.min(bottom, q.bottom);
    }
    return { left, right, top, bottom, width: right - left, height: bottom - top };
  };
  const ownText = (el) => [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
  const ellipsis = (el) => {
    for (let e = el; e && e !== document.body; e = e.parentElement) {
      if (getComputedStyle(e).textOverflow === "ellipsis") return true;
    }
    return false;
  };
  // an open phone menu covers the page on purpose
  const overlay = (el) => Boolean(el.closest(".sidebar.open, .backdrop"));

  if (document.documentElement.scrollWidth > W + 1) {
    found.push({ kind: "page-overflow", where: "document", detail: `${document.documentElement.scrollWidth}px wide in a ${W}px screen` });
  }
  // the outermost element that leaves the screen, unless a box scrolls it sideways
  for (const el of all) {
    const r = el.getBoundingClientRect();
    if ((r.right > W + 1 || r.left < -1) && !scroller(el)) {
      const p = el.parentElement.getBoundingClientRect();
      if (p.right > W + 1 || p.left < -1) continue;
      found.push({ kind: "offscreen", where: path(el), text: text(el), detail: `${Math.round(r.left)}..${Math.round(r.right)} of ${W}` });
    }
  }
  // content that leaves its card
  for (const card of document.querySelectorAll(".card")) {
    if (!shown(card) || hiddenMenu(card)) continue;
    const c = card.getBoundingClientRect();
    for (const el of card.querySelectorAll("*")) {
      if (!shown(el) || scroller(el) && scroller(el) !== card && card.contains(scroller(el))) continue;
      const r = el.getBoundingClientRect();
      if (r.right > c.right + 2 || r.left < c.left - 2) {
        const p = el.parentElement.getBoundingClientRect();
        if (p.right > c.right + 2 || p.left < c.left - 2) continue;
        found.push({ kind: "spill", where: path(el), text: text(el), detail: `${Math.round(r.right - c.right)}px past the card` });
      }
    }
  }
  // text cut off without an ellipsis, by its own box or one around it
  for (const el of all) {
    if (!ownText(el) || ellipsis(el)) continue;
    const s = getComputedStyle(el);
    const clips = ["hidden", "clip"].includes(s.overflowX);
    const r = el.getBoundingClientRect();
    const v = visible(el);
    if (clips && el.scrollWidth > el.clientWidth + 1) {
      found.push({ kind: "clipped", where: path(el), text: text(el), detail: `${el.scrollWidth}px of text in ${el.clientWidth}px` });
    } else if (v.width > 0 && v.width < r.width - 1 && !scroller(el)) {
      found.push({ kind: "clipped", where: path(el), text: text(el), detail: `${Math.round(v.width)} of ${Math.round(r.width)}px shown` });
    }
  }
  // boxes that scroll sideways when only tables, graphs and code are meant to
  for (const el of all) {
    const ox = getComputedStyle(el).overflowX;
    if ((ox === "auto" || ox === "scroll") && el.scrollWidth > el.clientWidth + 1
        && !el.matches(".table-wrap, .wf-graph, pre, code, .scroll-x")) {
      found.push({ kind: "scroll-x", where: path(el), text: text(el).slice(0, 30), detail: `${el.scrollWidth}px in ${el.clientWidth}px` });
    }
  }
  // controls on top of each other
  const controls = all.filter((el) => el.matches("a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=option], [role=tab]"));
  for (let i = 0; i < controls.length; i++) {
    const a = visible(controls[i]);
    for (let j = i + 1; j < controls.length; j++) {
      if (controls[i].contains(controls[j]) || controls[j].contains(controls[i])) continue;
      if (overlay(controls[i]) !== overlay(controls[j])) continue;
      const b = visible(controls[j]);
      const w = Math.min(a.right, b.right) - Math.max(a.left, b.left);
      const h = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
      if (w > 2 && h > 2) {
        found.push({ kind: "overlap", where: `${path(controls[i])}  ×  ${path(controls[j])}`, text: `${text(controls[i])} / ${text(controls[j])}`, detail: `${Math.round(w)}x${Math.round(h)}px` });
      }
    }
  }
  if (touch) {
    for (const el of controls) {
      // a link inside running text, and a box whose label is the target, are exempt (2.5.8)
      const inline = el.tagName === "A" && [...el.parentElement.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      const label = el.closest("label");
      const target = (el.type === "checkbox" || el.type === "radio") && label ? label : el;
      const r = target.getBoundingClientRect();
      if (!inline && (r.width < 24 || r.height < 24)) {
        found.push({ kind: "small-target", where: path(target), text: text(target), detail: `${Math.round(r.width)}x${Math.round(r.height)}px` });
      }
    }
  }
  for (const el of all) {
    const size = parseFloat(getComputedStyle(el).fontSize);
    if (ownText(el) && size < 11) {
      found.push({ kind: "tiny-text", where: path(el), text: text(el), detail: `${size}px` });
    }
  }
  return found;
}

async function open(page, how, lang) {
  if (how === "editor") {
    const edit = page.locator(".wf-edit-btn", { hasText: lang === "ko" ? "편집" : "Edit" }).first();
    if (await edit.isVisible()) {
      await edit.click();
      await page.waitForTimeout(600);
      return true;
    }
    return false;  // phones: editing needs a wider screen
  }
  if (how === "menu") {
    const menu = page.locator(".menu-btn");
    if (await menu.isVisible()) {
      await menu.click();
      await page.waitForTimeout(400);
      return true;
    }
    return false;
  }
  if (how === "trace") {
    const title = lang === "ko" ? "분기 포트폴리오 통합 리뷰" : "Quarterly portfolio review";
    await page.locator(".card", { hasText: title }).locator("button").first().click();
    await page.waitForSelector(lang === "ko" ? "text=인사이트 —" : "text=Insight —", { timeout: 20000 });
    await page.waitForTimeout(500);
    return true;
  }
  return true;
}

const browser = await chromium.launch({ channel: "chrome", headless: true });
const report = [];
for (const size of SIZES) {
  for (const theme of THEMES) {
    const ctx = await browser.newContext({
      viewport: { width: size.width, height: size.height }, colorScheme: theme,
      hasTouch: size.touch, isMobile: size.width < 768,
    });
    for (const lang of LANGS) {
      for (const p of await pages()) {
        const page = await ctx.newPage();
        const errors = [];
        page.on("console", (m) => { if (m.type() === "error") errors.push(m.text().slice(0, 160)); });
        page.on("pageerror", (e) => errors.push(String(e).slice(0, 160)));
        await page.goto(`${BASE}${p.path}${p.path.includes("?") ? "&" : "?"}lang=${lang}`);
        await page.waitForLoadState("networkidle");
        await page.waitForTimeout(500);
        if (!(await open(page, p.open, lang))) { await page.close(); continue; }
        const found = await page.evaluate(inspect, { touch: size.touch });
        for (const e of errors) found.push({ kind: "console", where: "console", detail: e });
        for (const f of found) report.push({ page: p.name, size: size.name, lang, theme, ...f });
        await page.close();
      }
    }
    await ctx.close();
  }
}
await browser.close();

// the same problem on several sizes, languages or themes is reported once, with where it shows
const grouped = new Map();
for (const r of report) {
  const key = `${r.kind}|${r.page}|${r.where}`;
  const g = grouped.get(key) ?? { kind: r.kind, page: r.page, where: r.where, text: r.text, detail: r.detail, seen: new Set() };
  g.seen.add(`${r.size}/${r.lang}/${r.theme}`);
  grouped.set(key, g);
}
const problems = [...grouped.values()].map((g) => ({ ...g, seen: [...g.seen].sort() }));
if (OUT) writeFileSync(OUT, JSON.stringify(problems, null, 1));
for (const p of problems) {
  console.log(`${p.kind.padEnd(13)} ${p.page.padEnd(16)} ${p.where}  ${p.text ? `"${p.text}" ` : ""}(${p.detail}) on ${p.seen.length}: ${p.seen.slice(0, 3).join(", ")}${p.seen.length > 3 ? ", …" : ""}`);
}
console.log(`${problems.length} layout problems`);
process.exit(problems.length ? 1 : 0);
