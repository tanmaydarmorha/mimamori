// Drives the real Mimamori web UI in visible Chrome windows, at a human pace, with a caption bar.
// The app is not touched: everything here is what a person could do with a mouse and keyboard.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

export const SPEEDS = { slow: 2, normal: 1, fast: 0.5 };
const WINDOWS = {
  teller: { x: 0, y: 0, width: 1280, height: 800 },
  phone: { x: 1290, y: 0, width: 480, height: 800 },
};
// --clean: footage for an edited video. Full-HD teller, taller phone, no caption bar (the edit adds its own);
// the cursor stays, and the captions go to a timeline file instead.
const CLEAN_WINDOWS = {
  teller: { x: 0, y: 0, width: 1920, height: 1080 },
  phone: { x: 1930, y: 0, width: 480, height: 960 },
};
const CLEAN_CSS = `#__demo_caption { display: none !important; } body { padding-bottom: 0 !important; }
  @media (max-width: 600px) { .phone { height: 100dvh !important; } }`;
const CHROME_UI = 90; // browser toolbar height on top of the page, so the page really is 800 high
const WAIT_MS = 90_000;
const THINKING = "The copilot is reading the conversation…";

export class Skip extends Error {}
export class StepError extends Error {}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// ---- the caption bar and the cursor: injected into the page, not part of the app -------------------

/** Idempotent: safe to call after every navigation. Uses the theme tokens (ink, washi). */
function installOverlay() {
  if (document.getElementById("__demo_caption")) return;
  const style = document.createElement("style");
  style.id = "__demo_style";
  style.textContent = `
    #__demo_caption { position: fixed; left: 0; right: 0; bottom: 0; z-index: 2147483647; box-sizing: border-box;
      min-height: 64px; padding: 12px 24px; background: #1B2A41; color: #F6F4EF; text-align: left;
      font: 20px/1.4 "BIZ UDPGothic", "Hiragino Sans", "Noto Sans JP", system-ui, sans-serif;
      opacity: 0; transition: opacity 150ms linear; pointer-events: none; display: flex; align-items: center; }
    body { padding-bottom: 96px !important; } /* lets the last controls scroll clear of the bar */
    @media (max-width: 600px) { /* full-height phone: pin it to the top and end it above a three-line caption */
      .phone-wrap { min-height: 0 !important; padding: 0 !important; align-items: flex-start !important; }
      .phone { height: calc(100dvh - 120px) !important; } }
    #__demo_cursor { position: fixed; z-index: 2147483646; width: 22px; height: 22px; margin: -11px 0 0 -11px; border-radius: 50%;
      background: rgba(31,122,122,.55); border: 2px solid #1F7A7A; pointer-events: none; left: -50px; top: -50px;
      transition: transform 120ms; }
    #__demo_cursor.down { transform: scale(.7); }`;
  document.documentElement.appendChild(style);
  const bar = document.createElement("div");
  bar.id = "__demo_caption";
  bar.setAttribute("aria-hidden", "true");
  document.documentElement.appendChild(bar);
  const cur = document.createElement("div");
  cur.id = "__demo_cursor";
  document.documentElement.appendChild(cur);
  addEventListener("mousemove", (e) => { cur.style.left = e.clientX + "px"; cur.style.top = e.clientY + "px"; }, true);
  addEventListener("mousedown", () => cur.classList.add("down"), true);
  addEventListener("mouseup", () => cur.classList.remove("down"), true);
}

// ---- one browser window ---------------------------------------------------------------------------

class Win {
  constructor(name, browser, context, page, run) {
    Object.assign(this, { name, browser, context, page, run });
    this.pos = { x: 100, y: 100 };
    this.caption = "";
  }

  async ensureOverlay() {
    await this.page.evaluate(installOverlay).catch(() => {});
  }

  async setCaption(text) {
    this.caption = text ?? "";
    await this.ensureOverlay();
    await this.page.evaluate((t) => {
      const bar = document.getElementById("__demo_caption");
      if (!bar) return;
      bar.textContent = t;
      bar.style.opacity = t ? "1" : "0";
    }, this.caption).catch(() => {});
  }

  async goto(url) {
    await this.page.goto(url, { waitUntil: "domcontentloaded" });
    await this.setCaption(this.caption); // re-inject after navigation
  }

  /** Scroll the element clear of the caption bar, glide the cursor to it, and pause before acting. */
  async moveTo(loc) {
    const { page } = this;
    await loc.waitFor({ state: "visible", timeout: WAIT_MS });
    await loc.evaluate((el) => {
      const r = el.getBoundingClientRect();
      if (r.top < 80 || r.bottom > innerHeight - 90) el.scrollIntoView({ block: "center", behavior: "instant" });
    });
    const box = await loc.boundingBox();
    if (!box) return;
    const to = { x: box.x + Math.min(box.width / 2, 60 + box.width * 0.2), y: box.y + box.height / 2 };
    const steps = Math.max(8, Math.round(22 * Math.min(1, this.run.f + 0.3)));
    for (let i = 1; i <= steps; i++) {
      const t = i / steps;
      const e = t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2; // ease in-out
      await page.mouse.move(this.pos.x + (to.x - this.pos.x) * e, this.pos.y + (to.y - this.pos.y) * e);
      await sleep(12);
    }
    this.pos = to;
    await sleep(600 * this.run.f);
  }

  async click(loc) {
    await this.moveTo(loc);
    await loc.click({ timeout: WAIT_MS });
  }

  async type(loc, text) {
    await this.moveTo(loc);
    await loc.click({ timeout: WAIT_MS });
    await loc.fill("");
    await loc.pressSequentially(text, { delay: 35 * this.run.f });
  }
}

// ---- targets: "button:Say this", "link:Analyst", "tab:Outreach", "text:…", or a CSS selector ------------

function locate(page, spec) {
  const m = /^(button|link|tab|label|text):(.*)$/s.exec(spec);
  if (!m) return page.locator(spec).first();
  const [, kind, name] = m;
  const exact = name.endsWith("!");
  const n = exact ? name.slice(0, -1) : name;
  if (kind === "label") return page.getByLabel(n, { exact }).first();
  if (kind === "text") return page.getByText(n, { exact }).first();
  return page.getByRole(kind, { name: n, exact }).first();
}

const asMatcher = (s) => {
  const m = /^\/(.*)\/([a-z]*)$/s.exec(s);
  return m ? new RegExp(m[1], m[2]) : s;
};

const subst = (v, vars) =>
  typeof v === "string" ? v.replace(/\$\{(\w+)\}/g, (_, k) => (k in vars ? vars[k] : `\${${k}}`)) : v;

async function until(fn, ms, label) {
  const end = Date.now() + ms;
  for (;;) {
    if (await fn()) return;
    if (Date.now() > end) throw new Error(`timed out after ${ms / 1000}s: ${label}`);
    await sleep(250);
  }
}

// ---- the scenario runner -------------------------------------------------------------------------

export async function runScenario(sc, { url, speed, record, outDir, clean = false }) {
  const f = SPEEDS[speed];
  const stamp = new Date().toISOString().replace(/[:.]/g, "-").slice(0, 19);
  const run = { f };
  const rawDir = path.join(outDir, `.raw-${sc.id}-${stamp}`);
  fs.mkdirSync(outDir, { recursive: true });

  const wins = {};
  for (const name of sc.windows ?? ["teller"]) {
    const g = (clean ? CLEAN_WINDOWS : WINDOWS)[name];
    const browser = await chromium.launch({
      channel: "chrome",
      headless: false,
      ignoreDefaultArgs: ["--enable-automation"],
      args: [`--window-position=${g.x},${g.y}`, `--window-size=${g.width},${g.height + CHROME_UI}`, "--no-first-run", "--disable-infobars", "--autoplay-policy=no-user-gesture-required"],
    });
    const context = await browser.newContext({
      viewport: { width: g.width, height: g.height },
      recordVideo: record ? { dir: rawDir, size: { width: g.width, height: g.height } } : undefined,
    });
    // The whole demo runs in the English UI so the glosses show. Set once; never overrides a later toggle.
    await context.addInitScript(() => {
      try { if (!localStorage.getItem("mimamori.lang")) localStorage.setItem("mimamori.lang", "en"); } catch {}
    });
    // The cursor and caption bar exist from the first paint; the runner also re-injects after each goto.
    await context.addInitScript(`addEventListener("DOMContentLoaded", ${installOverlay.toString()})`);
    if (clean) {
      await context.addInitScript((css) => addEventListener("DOMContentLoaded", () => {
        const s = document.createElement("style"); s.textContent = css; document.documentElement.appendChild(s);
      }), CLEAN_CSS);
    }
    const page = await context.newPage();
    page.on("pageerror", (e) => console.error(`  [${name}] page error: ${e.message}`));
    page.on("crash", () => console.error(`  [${name}] the page crashed`));
    wins[name] = new Win(name, browser, context, page, run);
  }

  const vars = { ...(sc.vars ?? {}) };
  const first = wins[sc.windows?.[0] ?? "teller"];
  let current = null;

  const result = { videos: [] };
  const t0 = Date.now();
  const timeline = []; // step starts, in seconds from the windows opening (≈ the start of each video)
  try {
    for (const [i, step] of sc.steps.entries()) {
      const label = `${i + 1} "${(typeof step.caption === "string" ? step.caption : Object.values(step.caption ?? {})[0] ?? step.name ?? "").slice(0, 48)}"`;
      current = label;
      const tStep = Date.now();
      const caps = typeof step.caption === "string" ? { [step.win ?? "teller"]: step.caption } : (step.caption ?? {});
      timeline.push({ step: i + 1, at: +((tStep - t0) / 1000).toFixed(2), captions: Object.fromEntries(Object.entries(caps).map(([w, t]) => [w, subst(t, vars)])) });
      for (const [w, text] of Object.entries(caps)) if (wins[w]) await wins[w].setCaption(subst(text, vars));
      for (const act of step.do ?? []) await doAction(act, wins, vars, url, f, sc);
      const hold = step.hold ?? 2500;
      await sleep(hold * f);
      if (process.env.DEMO_TIMING) console.log(`  step ${i + 1} took ${((Date.now() - tStep) / 1000).toFixed(1)}s (at ${((Date.now() - t0) / 1000).toFixed(1)}s): ${label}`);
    }
  } catch (err) {
    if (err instanceof Skip) { result.skipped = err.message; } else {
      for (const w of Object.values(wins)) {
        try { await w.page.screenshot({ path: path.join(outDir, `FAIL-${sc.id}-${w.name}-${stamp}.png`) }); } catch {}
        try { fs.writeFileSync(path.join(outDir, `FAIL-${sc.id}-${w.name}-${stamp}.txt`), `${w.page.url()}\n\n${(await w.page.content()).slice(0, 4000)}`); } catch {}
      }
      await closeAll(wins, record, rawDir, outDir, sc.id, stamp, result);
      throw new StepError(`${sc.id}: step ${current}: ${err.message}`);
    }
  }
  await closeAll(wins, record, rawDir, outDir, sc.id, stamp, result);
  if (record) {
    const file = path.join(outDir, `${sc.id}-timeline-${stamp}.json`);
    fs.writeFileSync(file, JSON.stringify({ scenario: sc.id, speed, clean, steps: timeline }, null, 2));
    result.videos.push(file);
  }
  return result;
}

async function closeAll(wins, record, rawDir, outDir, id, stamp, result) {
  for (const w of Object.values(wins)) {
    if (w.closed) continue;
    w.closed = true;
    const video = w.page.video();
    await w.context.close().catch(() => {});
    if (record && video) {
      const dest = path.join(outDir, `${id}-${w.name}-${stamp}.webm`);
      try { fs.renameSync(await video.path(), dest); result.videos.push(dest); } catch {}
    }
    await w.browser.close().catch(() => {});
  }
  if (record) fs.rmSync(rawDir, { recursive: true, force: true });
}

// ---- actions ---------------------------------------------------------------------------------------

async function doAction(raw, wins, vars, baseUrl, f, sc) {
  const tAct = Date.now();
  try { return await doActionInner(raw, wins, vars, baseUrl, f, sc); } finally {
    const ms = Date.now() - tAct;
    if (process.env.DEMO_TIMING && ms > 3000 * f + 1500) console.log(`    action ${raw.a} ${raw.target ?? raw.text ?? raw.path ?? ""} took ${(ms / 1000).toFixed(1)}s`);
  }
}

async function doActionInner(raw, wins, vars, baseUrl, f, sc) {
  const a = Object.fromEntries(Object.entries(raw).map(([k, v]) => [k, subst(v, vars)]));
  const w = wins[a.win ?? "teller"];
  if (!w) throw new Error(`scenario uses window "${a.win}" but declares only ${Object.keys(wins)}`);
  const page = w.page;
  const L = (spec) => locate(page, spec);

  switch (a.a) {
    case "goto":
      return w.goto(baseUrl.replace(/\/$/, "") + a.path);

    case "click":
      return w.click(L(a.target));

    case "type":
      return w.type(L(a.target), a.text);

    case "select":
      await w.moveTo(L(a.target));
      return L(a.target).selectOption(a.value);

    case "scroll": // bring something into the middle of the window so viewers can read it
      await L(a.target).waitFor({ state: "visible", timeout: WAIT_MS });
      return L(a.target).evaluate((el) => el.scrollIntoView({ block: "center", behavior: "smooth" }));

    case "hold":
      return sleep((a.ms ?? 1000) * f);

    case "wait": {
      const thinking = a.thinking === true;
      const before = w.caption;
      if (thinking) await w.setCaption(THINKING);
      let loc = L(a.target);
      if (a.text) loc = page.locator(a.target).filter({ hasText: asMatcher(a.text) }).first();
      try {
        await loc.waitFor({ state: "visible", timeout: a.timeout ?? WAIT_MS });
      } catch {
        throw new Error(`waited for ${a.target}${a.text ? ` with text ${a.text}` : ""}, never appeared (${(a.timeout ?? WAIT_MS) / 1000}s)`);
      }
      if (thinking) await w.setCaption(before);
      return;
    }

    case "expectNot": { // fail the scenario if this selector is present now (e.g. the band reached High)
      const n = await page.locator(a.target).count();
      if (n) throw new Error(a.message ?? `${a.target} is present, but it should not be`);
      return;
    }

    case "setVar": {
      const text = await L(a.target).textContent();
      vars[a.name] = (text ?? "").trim();
      return;
    }

    case "caseFromUrl": {
      await until(() => /\/case\/[^/?#]+/.test(page.url()), 15_000, "the case page to open");
      vars.caseId = /\/case\/([^/?#]+)/.exec(page.url())[1];
      return;
    }

    case "openTransfer": // open the "New counter transfer" form
      if (!(await page.locator('[data-testid="transfer-form"]').evaluate((el) => el.open))) await w.click(L('[data-testid="transfer-form"] summary'));
      return;

    case "transfer": { // the "New counter transfer" form; the defaults are the Tanaka demo transfer
      const form = '[data-testid="transfer-form"]';
      if (!(await page.locator(form).evaluate((el) => el.open))) await w.click(L(`${form} summary`));
      if (a.amount) await w.type(L(`${form} input[aria-label="Amount"]`), String(a.amount));
      // textContent() on an element that isn't there yet waits out Playwright's 30 s default: count first.
      const textOf = async (loc) => ((await loc.count()) ? await loc.first().textContent() : "") ?? "";
      const stale = await textOf(page.locator('[data-testid="transfer-result"]'));
      const tSubmit = Date.now();
      await w.click(L(`${form} button[type=submit]`));
      if (process.env.DEMO_TIMING) console.log(`    transfer: clicked submit after ${((Date.now() - tSubmit) / 1000).toFixed(1)}s`);
      const before = w.caption;
      await w.setCaption(a.waiting ?? "The bank is checking the transfer…");
      const result = page.locator('[data-testid="transfer-result"]');
      const refused = page.locator(`${form} [role=alert]`);
      await until(async () => {
        if (await refused.count()) return true;
        const t = await textOf(result);
        return t && t !== stale;
      }, WAIT_MS, "the transfer result");
      await w.setCaption(before);
      if (process.env.DEMO_TIMING) console.log(`    transfer: result shown ${((Date.now() - tSubmit) / 1000).toFixed(1)}s after the click began`);
      if (await refused.count()) {
        const why = ((await refused.first().textContent()) ?? "").trim();
        if (/frozen/i.test(why)) throw new Skip("The payee account was frozen by an earlier `hero` run (the freeze is permanent), so transfers to it are refused. Run with --fresh.");
        throw new Error(`the transfer was refused: ${why}`);
      }
      const text = await textOf(result);
      const opened = /Alert raised/.test(text);
      if (a.expect === "accepted" && opened) {
        if (a.skipIfAlerted) throw new Skip(a.skipIfAlerted);
        throw new Error("the transfer opened a case, but this step expects it to be accepted");
      }
      if (a.expect === "case" && !opened) throw new Error(`expected an alert, got: ${text}`);
      return;
    }

    case "turn": { // type a customer/teller turn in the conversation panel and send it
      const who = a.who === "teller" ? "Teller" : "Customer";
      const panel = '[data-testid="turn-panel"]';
      const before = await page.locator(`${panel} .turn`).count();
      await w.click(page.locator(`${panel} .seg label`).filter({ hasText: who }).first());
      await w.type(L(`${panel} input[aria-label="Turn text"]`), a.text);
      await sleep(400 * f);
      await w.click(L(`${panel} button[type=submit]`));
      await until(async () => (await page.locator(`${panel} .turn`).count()) > before, 30_000, "the turn to appear in the transcript");
      if (a.settle) { // the box empties once the server has finished the copilot's reading of this turn
        const prev = w.caption;
        await w.setCaption(THINKING);
        await until(async () => (await page.locator(`${panel} input[aria-label="Turn text"]`).inputValue()) === "", WAIT_MS, "the copilot to finish reading the turn");
        await w.setCaption(prev);
      }
      return;
    }

    case "phoneNotice": { // find the notice for THIS case (the code on the console), read its code
      const consoleCode = a.consoleCode
        ? (await (async (l) => ((await l.count()) ? await l.first().textContent() : ""))(wins.teller.page.locator('[data-testid="family-call"] p strong')) ?? "").trim()
        : "";
      const notices = page.locator('[data-testid="notice"]');
      const mine = consoleCode ? notices.filter({ has: page.locator('[data-testid="notice-code"]', { hasText: consoleCode }) }) : notices;
      await mine.first().waitFor({ state: "visible", timeout: WAIT_MS });
      vars[a.into ?? "code"] = ((await mine.first().locator('[data-testid="notice-code"]').textContent()) ?? "").trim();
      vars.__notice = consoleCode;
      return;
    }

    case "phoneDial": { // "Call the bank" → press 1 → key in the code → Call
      const notices = page.locator('[data-testid="notice"]');
      const mine = vars.__notice ? notices.filter({ has: page.locator('[data-testid="notice-code"]', { hasText: vars.__notice }) }) : notices;
      await w.click(mine.first().getByRole("button", { name: "Call the bank" }));
      await w.click(page.locator(".menu button").first());
      for (const d of String(a.code)) await w.click(page.locator(".keypad").getByRole("button", { name: d, exact: true }));
      await w.click(page.locator(".keypad").getByRole("button", { name: "Call", exact: true }));
      return;
    }

    case "phoneSay": { // the caller speaks one line (typed) and waits for the assistant's reply
      const chat = page.locator('[data-testid="phone-chat"] .bubble-agent');
      const before = await chat.count();
      await w.type(L('input[aria-label="Call speech"]'), a.text);
      await sleep(300 * f);
      await w.click(L(".turn-form button[type=submit]"));
      if (a.noReply) return;
      const prev = w.caption;
      await w.setCaption(THINKING.replace("The copilot is reading the conversation", "The assistant is working out a reply"));
      await until(async () => (await chat.count()) > before, WAIT_MS, "the assistant's reply on the phone");
      await w.setCaption(prev);
      return;
    }

    default:
      throw new Error(`unknown action "${a.a}" in scenario ${sc.id}`);
  }
}
