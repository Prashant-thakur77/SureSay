// Records SureSay's live web client as crisp frames (Chrome screencast, JPEG q92) and writes an exact-timed MP4.
// Usage: node video/rec.mjs <flow> [hub-url]. Each flow logs named marks (seconds) for the editor.
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { chromium } from "playwright-core";

const FLOW = process.argv[2];
const HUB = process.argv[3] || "https://fig5s4lcztnov5vd3us22pnmoi0srphu.lambda-url.us-east-1.on.aws";
const OUT = `${process.env.HOME}/Videos/suresay/clips`;
const FRAMES = `${OUT}/frames-${FLOW}`;
rmSync(FRAMES, { recursive: true, force: true });
mkdirSync(FRAMES, { recursive: true });

const browser = await chromium.launch({
  executablePath: `${process.env.HOME}/.cache/ms-playwright/chromium-1248/chrome-linux64/chrome`,
  args: ["--autoplay-policy=no-user-gesture-required",
         ...(process.env.FAKE_MIC ? ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
                                     `--use-file-for-fake-audio-capture=${process.env.FAKE_MIC}%noloop`] : [])],
});
const GRAPHICS = FLOW.startsWith("gfx-") || FLOW === "bubbles";
const ctx = await browser.newContext(GRAPHICS
  ? { viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 }
  : { viewport: { width: 1536, height: 864 }, deviceScaleFactor: 1.25, reducedMotion: "no-preference", colorScheme: "light",
      permissions: ["microphone"] });
const page = await ctx.newPage();
const cdp = await ctx.newCDPSession(page);
const frames = [];
let t0 = null;
cdp.on("Page.screencastFrame", async (f) => {
  const t = f.metadata.timestamp;
  if (t0 === null) t0 = t;
  const file = `${FRAMES}/${String(frames.length).padStart(5, "0")}.jpg`;
  writeFileSync(file, Buffer.from(f.data, "base64"));
  frames.push({ file, t: t - t0 });
  await cdp.send("Page.screencastFrameAck", { sessionId: f.sessionId }).catch(() => {});
});
const marks = {};
// Wall-clock marks on the screencast's own clock (its timestamps are epoch seconds): frames stop arriving while the
// page is still, so "the last frame's time" would be stale.
const mark = (name) => { marks[name] = t0 === null ? 0 : Date.now() / 1000 - t0; console.log("mark", name, marks[name].toFixed(2)); };
const wait = (ms) => page.waitForTimeout(ms);
const slowType = async (sel, text) => { await page.click(sel); for (const ch of text) { await page.keyboard.type(ch); await wait(70); } };

async function enterDemo() {
  await page.goto(HUB, { waitUntil: "networkidle" });
  await page.waitForSelector("text=How would you like to");
  await page.getByRole("button", { name: /start quietly/i }).first().click();
  await page.getByRole("button", { name: /try it now/i }).first().click();
  await page.waitForSelector(".guest-note", { timeout: 30000 });
  await wait(1500);
}

async function start() {
  await cdp.send("Page.startScreencast", { format: "jpeg", quality: 92, maxWidth: 1920, maxHeight: 1080, everyNthFrame: 1 });
  await wait(300);
}

const TIMELINE = () => JSON.parse(readFileSync(`${process.env.HOME}/Videos/suresay/build/timeline.json`, "utf8"));
const GFX = `file://${process.cwd()}/video/graphics.html`;

async function graphics(name) {
  const sc = TIMELINE().scenes.find((x) => x.name === name);
  const cues = Object.fromEntries(sc.lines.map((l) => [l.id, +(l.start - sc.start).toFixed(3)]));
  await page.goto(`${GFX}#scene=${name}&cues=${encodeURIComponent(JSON.stringify(cues))}`);
  await page.evaluate(() => document.fonts.ready);
  await start();
  mark("start");
  await page.evaluate(() => window.__start());
  await wait(sc.dur * 1000 + 300);
  mark("end");
}

const flows = {
  async people() {
    await enterDemo();
    await page.getByRole("tab", { name: "Talk to someone" }).click();
    await wait(800);
    await start();
    mark("start");
    await wait(1800);
    await page.locator(".talk__mic").click();
    mark("speaking");
    await page.waitForSelector(".btn--yes, button.card", { timeout: 40000 });
    mark("cards");
    await wait(3000);
    if (await page.locator(".btn--yes").count()) await page.locator(".btn--yes").first().click();
    else await page.keyboard.press("1");
    mark("chosen");
    await page.waitForSelector(".spoken__text", { timeout: 20000 });
    mark("spoken");
    await wait(2600);
    await page.getByRole("button", { name: /show it to them/i }).click();
    mark("listener");
    await wait(3600);
    await page.getByRole("button", { name: /turn it around/i }).click();
    mark("flipped");
    await wait(2600);
    mark("end");
  },
  async practice() {
    await enterDemo();
    await page.getByRole("tab", { name: "Practice" }).click();
    await page.waitForSelector(".practice__item");
    await wait(600);
    await start();
    mark("start");
    await wait(2000);
    await page.locator(".practice__item").first().click();
    mark("speaking");
    await page.waitForSelector(".practice__pct", { timeout: 40000 });
    mark("scored");
    await wait(4500);
    mark("end");
  },
  async help() {
    await enterDemo();
    await start();
    mark("start");
    await wait(1200);
    await page.getByRole("button", { name: "Help" }).click();
    mark("help");
    await page.waitForSelector("button.card", { timeout: 20000 });
    mark("cards");
    await wait(4000);
    mark("end");
  },
  "gfx-turn": () => graphics("turn"),
  "gfx-agent": () => graphics("agent"),
  "gfx-proof": () => graphics("proof"),
  "gfx-built": () => graphics("built"),
  async "gfx-end"() {
    await page.goto(`${GFX}#scene=end`);
    await page.evaluate(() => document.fonts.ready);
    await start();
    mark("start");
    await page.evaluate(() => window.__start());
    await wait(5200);
    mark("end");
  },
  async bubbles() {
    await page.goto(`${GFX}#scene=bubbles&clear=1`);
    await page.evaluate(() => document.fonts.ready);
    for (const id of ["b1", "b2", "b3"]) {
      await page.evaluate((keep) => document.querySelectorAll("#bubbles .b").forEach((b) => { b.style.visibility = b.id === keep ? "visible" : "hidden"; }), id);
      await page.screenshot({ path: `${OUT}/bubble_${id}.png`, omitBackground: true });
    }
    await start();
    await wait(200);
  },
  async demo() {
    await enterDemo();
    await start();
    mark("start");
    await wait(1200);
    mark("chip");
    await page.getByRole("button", { name: /van on/i }).first().click();
    await page.waitForSelector("button.card");
    mark("cards");
    await wait(4200);
    await page.keyboard.press("1");
    mark("chosen");
    await page.waitForSelector(".ticket", { timeout: 20000 });
    mark("receipt");
    await wait(4500);
    mark("end");
  },
  async door() {
    await enterDemo();
    await start();
    mark("start");
    await slowType("#type-input", "open the door");
    await page.keyboard.press("Enter");
    await page.waitForSelector("button.card");
    mark("cards");
    await wait(1500);
    await page.locator("button.card", { hasText: "Unlock the front door" }).first().click();
    mark("unlock_chosen");
    await page.waitForSelector("text=Say yes or no", { timeout: 20000 }).catch(() => {});
    mark("final");
    await wait(2600);
    await page.keyboard.press("Escape");
    mark("no");
    await wait(2600);
    mark("type_dont");
    await slowType("#type-input", "don't unlock the door");
    await page.keyboard.press("Enter");
    await page.waitForSelector("text=Nothing was changed", { timeout: 20000 });
    mark("unchanged");
    await wait(3500);
    mark("end");
  },
  async features() {
    await enterDemo();
    const user = await page.evaluate(() => JSON.parse(localStorage.getItem("suresay.device") || "{}").user_id);
    const linked = spawnSync(`${process.cwd()}/.venv/bin/python`, ["video/link_guest.py", user], { encoding: "utf8" });
    console.log(linked.stdout.trim(), linked.stderr.slice(-300));
    await start();
    mark("start");
    await page.getByRole("tab", { name: "Speak for me" }).click();
    await wait(1500);
    mark("board");
    await page.locator("button", { hasText: /thirsty/i }).first().click();
    await page.waitForSelector(".btn--yes", { timeout: 20000 });
    mark("tile_card");
    await wait(1600);
    await page.locator(".btn--yes").first().click();
    mark("spoken");
    await wait(900);
    await page.evaluate(() => window.scrollTo({ top: 0, behavior: "smooth" }));
    await wait(3600);
    await page.getByRole("tab", { name: "Talk" }).click();
    await wait(600);
    await page.getByRole("button", { name: /settings/i }).first().click();
    await wait(700);
    await page.locator(".dialog .doormenu > button").first().click();
    await wait(500);
    await page.locator(".dialog .doormenu__item", { hasText: /ravi/i }).first().click();
    await page.waitForSelector("button.card", { timeout: 20000 });
    mark("doorbell");
    await wait(4200);
    await page.keyboard.press("2");
    await wait(3500);
    await page.getByRole("tab", { name: "Timeline" }).click();
    mark("timeline");
    await wait(3800);
    await page.getByRole("button", { name: /settings/i }).first().click();
    await wait(900);
    await page.locator("fieldset.devices").evaluate((el) => el.scrollIntoView({ block: "start" }));
    mark("devices");
    await wait(3600);
    mark("end");
  },
};

await flows[FLOW]();
await cdp.send("Page.stopScreencast");
await browser.close();

// Exact-timed video: each frame lasts until the next one (screencast only sends frames when something changes).
const list = frames.map((f, i) => `file '${f.file}'\nduration ${((frames[i + 1]?.t ?? f.t + 0.5) - f.t).toFixed(4)}`).join("\n");
writeFileSync(`${FRAMES}/list.txt`, `${list}\nfile '${frames[frames.length - 1].file}'\n`);
const r = spawnSync("ffmpeg", ["-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", `${FRAMES}/list.txt`,
  "-vf", "scale=1920:1080:flags=lanczos,fps=30,format=yuv420p", "-c:v", "libx264", "-crf", "16", "-preset", "medium",
  `${OUT}/${FLOW}.mp4`], { stdio: "inherit" });
writeFileSync(`${OUT}/${FLOW}.marks.json`, JSON.stringify(marks, null, 1));
console.log(FLOW, frames.length, "frames,", (frames.at(-1)?.t ?? 0).toFixed(1), "s; ffmpeg", r.status);
