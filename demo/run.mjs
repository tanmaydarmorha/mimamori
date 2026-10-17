// Usage (via scripts/demo.sh):  node run.mjs <scenario|all> [--record] [--clean] [--hq] [--speed slow|normal|fast] [--url URL]
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { runScenario, SPEEDS, Skip, StepError } from "./lib/driver.mjs";

const here = path.dirname(fileURLToPath(import.meta.url));
const ORDER = ["split", "small", "genuine", "impostor", "hero-en", "hero"]; // works on a fresh stack: see README
// `video`: the English footage for the submission video (English-only rule), recorded with --record --clean.
const VIDEO = ["split", "small", "genuine-en", "impostor-en", "hero-en-full"];
const KNOWN = [...ORDER, ...VIDEO.filter((id) => !ORDER.includes(id))];
const load = (id) => JSON.parse(fs.readFileSync(path.join(here, "scenarios", `${id}.json`), "utf8"));

const args = process.argv.slice(2);
const flag = (n) => args.includes(`--${n}`);
const opt = (n, d) => { const i = args.indexOf(`--${n}`); return i >= 0 ? args[i + 1] : d; };
const target = args.find((a, i) => !a.startsWith("--") && !(i > 0 && ["--speed", "--url"].includes(args[i - 1])));

if (!target) {
  console.log("Scenarios:\n");
  for (const id of KNOWN) { const s = load(id); console.log(`  ${id.padEnd(9)} ${s.story}${s.needsFresh ? "  [needs --fresh]" : ""}`); }
  console.log("\nscripts/demo.sh <scenario|all|video> [--fresh] [--record] [--clean] [--hq] [--speed slow|normal|fast] [--url URL]");
  process.exit(0);
}
const ids = target === "all" ? ORDER : target === "video" ? VIDEO : [target];
for (const id of ids) if (!KNOWN.includes(id)) { console.error(`Unknown scenario "${id}". Run scripts/demo.sh with no argument for the list.`); process.exit(2); }
const speedArg = opt("speed", null);
if (speedArg && !(speedArg in SPEEDS)) { console.error("--speed must be slow, normal or fast"); process.exit(2); }

const url = opt("url", "http://localhost:8080");
const outDir = path.join(here, "out");
const summary = [];
for (const id of ids) {
  const sc = load(id);
  const speed = speedArg ?? sc.speed ?? "normal";
  console.log(`\n▶ ${id} (${speed}) — ${sc.story}`);
  const t0 = Date.now();
  try {
    const r = await runScenario(sc, { url, speed, record: flag("record"), outDir, clean: flag("clean"), hq: flag("hq") });
    const secs = Math.round((Date.now() - t0) / 1000);
    if (r.skipped) { console.log(`  skipped: ${r.skipped}`); summary.push([id, "skipped", r.skipped]); }
    else { console.log(`  done in ${secs}s`); summary.push([id, "ok", `${secs}s`]); }
    for (const v of r.videos) console.log(`  ${v.endsWith(".json") ? "timeline" : "video"}: ${path.relative(process.cwd(), v)}`);
  } catch (e) {
    console.error(`  FAILED — ${e.message}`);
    summary.push([id, "FAILED", e.message]);
  }
}
if (ids.length > 1) { console.log("\nSummary"); for (const [id, st, note] of summary) console.log(`  ${st.padEnd(8)} ${id.padEnd(9)} ${st === "ok" ? note : ""}`); }
process.exit(summary.some(([, st]) => st === "FAILED") ? 1 : 0);
