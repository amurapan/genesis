/** Record actual browser and terminal interactions on an isolated X11 display.
 * Requires Playwright Core, Chrome, Xvfb, xterm, uv, MSS 10.1.0 and FFmpeg.
 * Start Xvfb and the static web server first; see docs/submission.md.
 */
import { spawn } from "node:child_process";
import {
  mkdir,
  writeFile,
  readFile,
  rm,
  mkdtemp,
  access,
} from "node:fs/promises";
import { resolve } from "node:path";
import { tmpdir } from "node:os";
import assert from "node:assert/strict";
const { chromium } = await import(
  process.env.PLAYWRIGHT_MODULE || "playwright-core"
);
const root = resolve(import.meta.dirname, ".."),
  out = resolve(root, "artifacts/live-demo");
const display = process.env.DISPLAY || ":98",
  base = process.env.DEMO_URL || "http://127.0.0.1:4174";
await mkdir(out, { recursive: true });
const introOnly = process.argv.includes("--intro-only");
const previous = introOnly
  ? JSON.parse(await readFile(resolve(out, "recording.json"), "utf8"))
  : null;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const exists = async (p) => {
  try {
    await access(p);
    return true;
  } catch {
    return false;
  }
};
const waitExit = (p) =>
  new Promise((r, j) => {
    p.once("error", j);
    p.once("exit", (code) =>
      code === 0 ? r() : j(new Error(`process exit ${code}`)),
    );
  });
const profile = await mkdtemp(resolve(tmpdir(), "evidable-video-"));
await mkdir(resolve(profile, "Default"), { recursive: true });
await writeFile(
  resolve(profile, "Default/Preferences"),
  JSON.stringify({
    translate: { enabled: false },
    intl: { accept_languages: "ru-RU,ru,en-US,en" },
  }),
);
const context = await chromium.launchPersistentContext(profile, {
  executablePath:
    process.env.CHROME_BINARY ||
    "/run/current-system/sw/bin/google-chrome-stable",
  headless: false,
  chromiumSandbox: true,
  viewport: null,
  args: [
    "--app=" + base,
    "--window-size=1600,900",
    "--window-position=0,0",
    "--force-device-scale-factor=1.2",
    "--enable-unsafe-swiftshader",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--disable-features=Translate,TranslateUI",
    "--lang=ru-RU",
    "--no-first-run",
    "--no-default-browser-check",
  ],
  ignoreDefaultArgs: ["--enable-automation", "about:blank"],
  env: { ...process.env, DISPLAY: display },
});
const page =
  context.pages().find((p) => p.url().startsWith(base)) || context.pages()[0];
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
const cdp = await context.newCDPSession(page);
const win = await cdp.send("Browser.getWindowForTarget");
await cdp.send("Browser.setWindowBounds", {
  windowId: win.windowId,
  bounds: { left: 0, top: 0, width: 1600, height: 900, windowState: "normal" },
});
await page.goto(base, { waitUntil: "networkidle" });
await sleep(700);
await page.bringToFront();
await page.waitForFunction(
  () => window.sledFilm && !sledFilm.snapshot().loading,
);
assert.equal(await page.evaluate(() => sledFilm.snapshot().mode), "cinematic");
await page.evaluate(() => scrollTo({ top: 0, behavior: "instant" }));
await page.waitForFunction(() => sledFilm.snapshot().progress < 0.001);
const segments = [];
let recorder, terminal;
async function segment(id, seconds, action) {
  const stop = resolve(out, `${id}.stop`);
  await rm(stop, { force: true });
  const target = resolve(out, `${id}.mp4`);
  recorder = spawn(
    "uv",
    [
      "run",
      "--no-project",
      "--python",
      "3.11",
      "--with",
      "mss==10.1.0",
      "python",
      "scripts/capture_screen.py",
      target,
      "--display",
      display,
      "--stop-file",
      stop,
    ],
    { cwd: root, stdio: ["ignore", "pipe", "inherit"] },
  );
  const exited = waitExit(recorder);
  exited.catch(() => {});
  await new Promise((yes, no) => {
    let buf = "";
    recorder.stdout.on("data", (d) => {
      buf += d;
      if (buf.includes("READY")) yes();
    });
    recorder.once("exit", (c) =>
      no(new Error(`capture failed before ready: ${c}`)),
    );
    recorder.once("error", no);
  });
  console.log("RECORDING " + id);
  const start = performance.now();
  try {
    await action();
    await sleep(Math.max(0, seconds * 1000 - (performance.now() - start)));
  } finally {
    await writeFile(stop, "stop");
    await exited;
    recorder = null;
  }
  const meta = JSON.parse(
    await readFile(target.replace(".mp4", ".capture.json"), "utf8"),
  );
  segments.push({ id, file: target, seconds: meta.seconds });
  if (!introOnly)
    await writeFile(
      resolve(out, "segments.json"),
      JSON.stringify(segments, null, 2) + "\n",
    );
  console.log("RECORDED " + id + " " + meta.seconds.toFixed(2) + "s");
}
async function terminalSegment(caseId, seconds) {
  const start = resolve(out, caseId + ".start"),
    done = resolve(out, caseId + ".done");
  await rm(start, { force: true });
  await rm(done, { force: true });
  terminal = spawn(
    "xterm",
    [
      "-geometry",
      "180x60+0+0",
      "-fa",
      "JetBrains Mono",
      "-fs",
      "16",
      "-b",
      "48",
      "-bw",
      "0",
      "-bg",
      "#080d0b",
      "-fg",
      "#e6f2e9",
      "-cr",
      "#a9efbe",
      "-title",
      "evidable — запуск среды",
      "-e",
      "python3",
      "scripts/demo_walkthrough.py",
      caseId,
      "--start-file",
      start,
      "--done-file",
      done,
    ],
    { cwd: root, env: { ...process.env, DISPLAY: display }, stdio: "ignore" },
  );
  await sleep(1000);
  try {
    await segment(caseId + "-cli", seconds, async () => {
      await writeFile(start, "start");
      const deadline = Date.now() + 15000;
      while (!(await exists(done))) {
        if (Date.now() > deadline) throw new Error("CLI timeout");
        await sleep(100);
      }
      const r = JSON.parse(await readFile(done, "utf8"));
      assert.equal(r.exit_code, 0);
      assert.equal(r.summary.evaluation.f1, 1);
      assert.equal(r.summary.evaluation.fp, 0);
      assert.equal(r.summary.evaluation.tp, caseId === "fx" ? 2 : 0);
    });
  } finally {
    terminal.kill("SIGTERM");
    terminal = null;
    await sleep(400);
  }
}
const evidence = (id) => page.locator(`.evidence-link[data-proof="${id}"]`);
try {
  await segment("01-intro", 12, async () => {
    await sleep(5500);
    await page.evaluate(async () => {
      let f = document.querySelector("#film"),
        s = document.querySelector("#film-stage"),
        target = (f.offsetHeight - s.offsetHeight) * 0.19,
        start = performance.now();
      await new Promise((done) => {
        function frame(now) {
          let t = Math.min(1, (now - start) / 2200);
          scrollTo({
            top: target * (t * t * (3 - 2 * t)),
            behavior: "instant",
          });
          if (t < 1) requestAnimationFrame(frame);
          else done();
        }
        requestAnimationFrame(frame);
      });
    });
  });
  if (introOnly) {
    previous.segments[0] = segments[0];
    previous.intro_graphics = await page.evaluate(
      () => sledFilm.snapshot().graphics,
    );
    await writeFile(
      resolve(out, "segments.json"),
      JSON.stringify(previous.segments, null, 2) + "\n",
    );
    await writeFile(
      resolve(out, "recording.json"),
      JSON.stringify(previous, null, 2) + "\n",
    );
  } else {
    await terminalSegment("fx", 23);
    await page.goto(base + "/lab.html?episode=fx-period#workspace", {
      waitUntil: "networkidle",
    });
    await page.locator(".paper-total").waitFor();
    await segment("03-laboratory", 30, async () => {
      await sleep(4500);
      await page
        .locator('.related-documents [data-proof="doc:payment-doc-1"]')
        .click();
      await sleep(6000);
      await page.locator('[data-action="play"]').click();
      await page.waitForFunction(
        () => document.querySelectorAll(".finding").length === 2,
        null,
        { timeout: 18000 },
      );
      assert.equal(await page.locator("#replay-range").inputValue(), "6");
      await page.locator('[data-tab="documents"]').click();
      await page.locator("#document-select").selectOption("1");
      await page.locator("#results").evaluate((e) => (e.scrollTop = 0));
    });
    await segment("04-evidence", 27, async () => {
      await evidence("ledger:r3").click();
      await sleep(8500);
      await evidence("fx:2026-11-30:USD:KZT").click();
      await sleep(8000);
      await page.locator('[data-finding="1"]').click();
      await evidence("manifest:episode").click();
      assert.match(
        await page.locator(".finding-value").textContent(),
        /45\s000,00/,
      );
    });
    await terminalSegment("clean", 18);
    await page.goto(base + "/lab.html#verification", {
      waitUntil: "networkidle",
    });
    await segment("06-verification", 18, async () => {
      await sleep(10000);
      await page.goto(base + "/lab.html#architecture", {
        waitUntil: "networkidle",
      });
    });
    await page.goto(base + "/lab.html#guide", { waitUntil: "networkidle" });
    await page.locator(".local-launch").scrollIntoViewIfNeeded();
    await segment("07-reproduce", 9, async () => {});
    assert.deepEqual(errors, []);
    const publicData = JSON.parse(
      await readFile(resolve(root, "web/data/demo.json"), "utf8"),
    );
    for (const [slug, caseId] of [
      ["fx-period", "fx"],
      ["clean", "clean"],
    ]) {
      const actual = JSON.parse(
        await readFile(
          resolve(out, `runs/${caseId}/private/report.json`),
          "utf8",
        ),
      );
      assert.deepEqual(
        actual.submission,
        publicData.cases.find((x) => x.id === slug).submission,
      );
    }
    await writeFile(
      resolve(out, "recording.json"),
      JSON.stringify(
        {
          segments,
          errors,
          browser: context.browser()?.version(),
          display,
          base,
          source:
            "Actual X11 recording of browser interactions and freshly executed Python CLI runs",
          public_submissions_match_actual_runs: true,
        },
        null,
        2,
      ) + "\n",
    );
    console.log(
      "DONE " + segments.reduce((n, s) => n + s.seconds, 0).toFixed(2) + "s",
    );
  }
} finally {
  if (recorder) recorder.kill("SIGTERM");
  if (terminal) terminal.kill("SIGTERM");
  await context.close();
  await rm(profile, { recursive: true, force: true });
}
